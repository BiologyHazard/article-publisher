"""Regression checks against captured Skland requests, without network writes."""

import io
import json
import tempfile
import unittest
from argparse import ArgumentParser
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from loguru import logger

from article_publisher.cli import _add_skland_options
from article_publisher.converters.markdown import MarkdownConverter
from article_publisher.document import (
    Alignment,
    Block,
    Blockquote,
    CodeBlock,
    Divider,
    Document,
    Formula,
    Heading,
    ImageBlock,
    InlineElement,
    ListItem,
    OrderedList,
    Paragraph,
    TextRun,
    UnorderedList,
)
from article_publisher.platforms.skland.client import SklandClient, UploadedImage
from article_publisher.platforms.skland.publisher import (
    SklandPublishConfig,
    SklandPublisher,
)

DOCS = Path(__file__).resolve().parents[1] / "docs"


def read_example(name: str) -> dict[str, Any]:
    return json.loads(
        (DOCS / f"skland_{name}_example.json").read_text(encoding="utf-8")
    )


def paragraph(text: str, align: Alignment = Alignment.LEFT) -> Paragraph:
    return Paragraph([TextRun(text)], align=align)


def list_item(text: str, *nested: Block) -> ListItem:
    return ListItem([paragraph(text), *nested])


def canonical_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the captured API graph, verifying ownership and reachability.

    Random IDs and map insertion order do not affect the visible document.
    Duplicate children, dangling references, and orphan blocks are errors.
    """
    block_map = document["blockMap"]
    visited: set[str] = set()
    item_ids: set[str] = set()

    def resolve(block_id: str, parent_id: str) -> dict[str, Any]:
        if block_id in visited:
            raise AssertionError(f"Duplicate block: {block_id}")
        visited.add(block_id)
        block = block_map[block_id]
        if block["id"] != block_id or block["parentId"] != parent_id:
            raise AssertionError(f"Invalid ownership: {block_id}")
        kind = block["kind"]
        content = block[kind]
        result = {"kind": kind, "align": block["align"]}
        if kind == "quote":
            result[kind] = [resolve(child, block_id) for child in content["childIds"]]
        elif kind == "list":
            if content["id"] != block_id:
                raise AssertionError("Invalid list ID")
            if set(content["itemIds"]) != set(content["itemMap"]):
                raise AssertionError("Orphan list item")
            items = []
            for item_id in content["itemIds"]:
                if item_id in item_ids or item_id in block_map:
                    raise AssertionError("Duplicate list item ID")
                item_ids.add(item_id)
                item = content["itemMap"][item_id]
                if item["id"] != item_id:
                    raise AssertionError("Invalid item ID")
                items.append([resolve(child, item_id) for child in item["childIds"]])
            result[kind] = {"kind": content["kind"], "items": items}
        else:
            result[kind] = content
        return result

    result = [resolve(block_id, document["id"]) for block_id in document["blockIds"]]
    if visited != set(block_map):
        raise AssertionError("Orphan blocks")
    return result


def captured_content() -> list[Block]:
    """The supported rich-text section of the user's captured editor document."""
    return [
        Paragraph([TextRun("粗体", bold=True)]),
        Paragraph([TextRun("斜体", italic=True)]),
        Paragraph([TextRun("粗斜体", bold=True, italic=True)]),
        Paragraph([TextRun("下划线", underline=True)]),
        Paragraph([TextRun("删除线", strikethrough=True)]),
        Paragraph(
            [
                TextRun("无黑"),
                TextRun("绿", color="#90C208"),
                TextRun("蓝", color="#46AAFA"),
                TextRun("红", color="#FA6E5A"),
                TextRun("橙", color="#FAB446"),
                TextRun("紫", color="#826EFF"),
            ]
        ),
        Heading(1, paragraph("H1")),
        Heading(2, paragraph("H2")),
        Heading(3, paragraph("H3")),
        Blockquote([paragraph("引用"), paragraph("与上一行属于同一个引用")]),
        Blockquote([paragraph("与上一行属于不同引用")]),
        paragraph("左对齐"),
        paragraph("居中对齐", Alignment.CENTER),
        paragraph("右对齐", Alignment.RIGHT),
        OrderedList(
            [
                list_item("1"),
                list_item(
                    "2",
                    OrderedList(
                        [
                            list_item("2.a"),
                            list_item(
                                "2.b",
                                OrderedList([list_item("2.b.i"), list_item("2.b.ii")]),
                            ),
                            list_item("2.c", UnorderedList([list_item("无序列表")])),
                        ]
                    ),
                ),
            ]
        ),
        UnorderedList(
            [
                list_item("1"),
                list_item(
                    "2",
                    OrderedList(
                        [
                            list_item("2.a"),
                            list_item("2.b", UnorderedList([list_item("2.b.i")])),
                        ]
                    ),
                ),
            ]
        ),
    ]


class SklandEditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logger.disable("article_publisher")
        self.addCleanup(logger.enable, "article_publisher")
        self.client = AsyncMock(spec=SklandClient)
        self.detail = read_example("获取已发布文章")["data"]
        self.client.get_item_detail.return_value = self.detail
        self.client.update_item.return_value = {}
        self.publisher = SklandPublisher(
            self.client, SklandPublishConfig(item_id="6411493")
        )

    async def publish_blocks(self, blocks: list[Block]) -> dict[str, Any]:
        await self.publisher.publish(Document("Updated title", blocks, None))
        return self.client.update_item.call_args.args[0]

    async def test_rich_text_matches_captured_create_and_edit_requests(self) -> None:
        for name in ("发布文章", "编辑已发布文章"):
            with self.subTest(example=name):
                content = captured_content()
                if name == "发布文章":
                    # The create capture explicitly colors 黑; the edit capture
                    # instead merges 无黑 into a single unstyled run.
                    colors = content[5]
                    assert isinstance(colors, Paragraph)
                    colors.children = [
                        TextRun("无"),
                        TextRun("黑", color="#222222"),
                        *colors.children[1:],
                    ]
                    for level in range(1, 4):
                        content[5 + level] = Heading(
                            level, Paragraph([TextRun(f"H{level}", color="#222222")])
                        )
                payload = await self.publish_blocks(content)
                actual = canonical_document(payload["document"])
                expected = canonical_document(read_example(name)["document"])
                # First ten roots are platform-specific content and divider variants.
                self.assertEqual(actual, expected[10:])

    async def test_metadata_and_document_identity_are_preserved(self) -> None:
        self.detail["item"]["volumeId"] = "existing-volume"
        self.detail["item"]["prePublishOn"] = True
        payload = await self.publish_blocks(captured_content())
        for key in (
            "gameId",
            "cateId",
            "volumeId",
            "origin",
            "viewKind",
            "downloadEnable",
            "prePublishOn",
            "publishedAtTs",
            "isAIGCStatementOn",
        ):
            self.assertEqual(payload[key], self.detail["item"][key])
        self.assertEqual(payload["tags"], self.detail["tags"])
        self.assertEqual(payload["tagIds"], [tag["id"] for tag in self.detail["tags"]])
        self.assertEqual(
            payload["document"]["id"], self.detail["item"]["document"]["id"]
        )
        self.assertEqual(payload["title"], "Updated title")
        self.assertEqual(payload["id"], "6411493")
        self.assertNotIn("coverImageId", payload)
        self.assertEqual(payload["cover"], {})
        canonical_document(payload["document"])

    async def test_article_does_not_resubmit_aggregated_media_from_detail(self) -> None:
        # GET item aggregates media from the old document and returns extra
        # response-only properties, including string dimensions and CDN variants.
        # The official article editor submits empty top-level media lists.
        self.detail["item"]["imageList"] = [
            {
                "id": "old-image",
                "url": "https://example.com/old.webp",
                "width": "4400",
                "height": "2475",
                "size": "178578",
                "format": "webp",
                "infos": [{"style": "origin"}],
            }
        ]
        self.detail["item"]["videoList"] = [{"id": "old-video"}]
        payload = await self.publish_blocks(captured_content())
        self.assertEqual(payload["imageList"], [])
        self.assertEqual(payload["videoList"], [])
        self.assertEqual(payload["viewKind"], 3)
        canonical_document(payload["document"])

    async def test_no_collection_omits_volume_id(self) -> None:
        for volume_id in (None, ""):
            with self.subTest(volume_id=volume_id):
                self.detail["item"]["volumeId"] = volume_id
                payload = await self.publish_blocks([paragraph("updated body")])
                self.assertNotIn("volumeId", payload)
        self.detail["item"].pop("volumeId")
        payload = await self.publish_blocks([paragraph("updated body")])
        self.assertNotIn("volumeId", payload)

    async def test_explicit_metadata_overrides(self) -> None:
        self.publisher = SklandPublisher(
            self.client,
            SklandPublishConfig(
                item_id="6411493", game_id=1, cate_id=4, publish_time="1800000000"
            ),
        )
        payload = await self.publish_blocks([paragraph("text")])
        self.assertEqual((payload["gameId"], payload["cateId"]), (1, 4))
        self.assertTrue(payload["prePublishOn"])
        self.assertEqual(payload["publishedAtTs"], "1800000000")

    async def test_cropped_cover_keeps_its_own_id(self) -> None:
        # The failing real request used the source image ID for both fields.
        # The detail response instead has a distinct ID for the cropped cover.
        self.detail["item"]["coverImageId"] = "original-image"
        self.detail["item"]["cover"] = {
            "id": "cropped-cover",
            "width": "3300",
            "height": "2475",
            "url": "https://example.com/cropped.webp",
        }
        image = next(
            block
            for block in self.detail["item"]["document"]["blockMap"].values()
            if block["kind"] == "image"
        )
        image["image"]["id"] = "original-image"
        with patch.object(self.publisher, "_convert_to_blocks", return_value=[image]):
            payload = await self.publish_blocks([paragraph("updated body")])
        self.assertEqual(payload["coverImageId"], "original-image")
        self.assertEqual(payload["cover"], {"id": "cropped-cover"})
        self.client.upload_image.assert_not_awaited()

    def test_missing_crop_lets_server_generate_cover(self) -> None:
        images = [{"kind": "image", "image": {"id": "original-image"}}]
        for cover in (None, {}, {"id": ""}):
            with self.subTest(cover=cover):
                payload = self.publisher._resolve_edit_cover(
                    images, "original-image", (cover or {}).get("id")
                )
                self.assertEqual(payload["coverImageId"], "original-image")
                self.assertEqual(payload["cover"], {})

    def test_replaced_images_invalidate_old_cover_and_crop(self) -> None:
        images = [
            {"kind": "image", "image": {"id": "new-first"}},
            {"kind": "image", "image": {"id": "new-second"}},
        ]
        self.assertEqual(
            self.publisher._resolve_edit_cover(images, "old-original", "old-crop"),
            {"coverImageId": "new-first", "cover": {}},
        )
        self.assertEqual(
            self.publisher._resolve_edit_cover(images, None, None),
            {"coverImageId": "new-first", "cover": {}},
        )

    def test_existing_cover_can_be_a_later_body_image(self) -> None:
        images = [
            {"kind": "image", "image": {"id": "first"}},
            {"kind": "image", "image": {"id": "selected"}},
        ]
        self.assertEqual(
            self.publisher._resolve_edit_cover(images, "selected", "cropped"),
            {"coverImageId": "selected", "cover": {"id": "cropped"}},
        )

    async def test_absent_cover_does_not_send_an_empty_image_id(self) -> None:
        self.detail["item"].pop("coverImageId", None)
        self.detail["item"].pop("cover", None)
        payload = await self.publish_blocks([paragraph("updated body")])
        self.assertNotIn("coverImageId", payload)
        self.assertEqual(payload["cover"], {})

    async def test_new_document_id_and_dry_run_have_valid_graphs(self) -> None:
        self.detail["item"].pop("document")
        payload = await self.publish_blocks(captured_content())
        canonical_document(payload["document"])
        self.client.reset_mock()
        output = io.StringIO()
        with redirect_stdout(output):
            result = await self.publisher.publish(
                Document("Preview", captured_content(), None), dry_run=True
            )
        preview = json.loads(output.getvalue())
        canonical_document(preview["document"])
        self.assertEqual(result["status"], "dry_run")
        self.assertGreater(len(output.getvalue()), 3000)
        self.client.get_item_detail.assert_not_awaited()
        self.client.upload_image.assert_not_awaited()
        self.client.update_item.assert_not_awaited()

    async def test_nested_quotes_and_multi_paragraph_list_items_keep_order(
        self,
    ) -> None:
        payload = await self.publish_blocks(
            [
                Blockquote(
                    [
                        paragraph("outer"),
                        Blockquote([paragraph("inner")]),
                        paragraph("end"),
                    ]
                ),
                OrderedList(
                    [
                        ListItem(
                            [
                                paragraph("first"),
                                paragraph("second", Alignment.RIGHT),
                                Heading(
                                    4,
                                    Paragraph(
                                        [TextRun("deep", italic=True)], Alignment.CENTER
                                    ),
                                ),
                            ]
                        ),
                        ListItem([]),
                    ]
                ),
                Paragraph([]),
            ]
        )
        tree = canonical_document(payload["document"])
        quote = tree[0]["quote"]
        self.assertEqual(
            [child["text"]["inlineElements"][0]["text"]["text"] for child in quote],
            ["outer", "inner", "end"],
        )
        items = tree[1]["list"]["items"]
        self.assertEqual(len(items[0]), 3)
        self.assertEqual(items[0][1]["align"], "right")
        heading = items[0][2]
        self.assertEqual(heading["align"], "center")
        self.assertEqual(heading["text"]["kind"], "body")
        self.assertEqual(
            heading["text"]["inlineElements"],
            [{"kind": "text", "text": {"text": "deep"}, "bold": True, "italic": True}],
        )
        self.assertEqual(items[1][0]["text"], tree[2]["text"])

    async def test_code_and_formula_fallbacks_preserve_content(self) -> None:
        payload = await self.publish_blocks(
            [CodeBlock("python", "first\n\n```\nlast"), Paragraph([Formula("x^2")])]
        )
        tree = canonical_document(payload["document"])
        self.assertEqual(
            [block["text"]["inlineElements"][0]["text"]["text"] for block in tree],
            ["````python", "first", "", "```", "last", "````", "x^2"],
        )

    async def test_inline_styles_combine_with_colors_and_link_fallback(self) -> None:
        payload = await self.publish_blocks(
            [
                Paragraph(
                    [
                        TextRun(
                            "link",
                            bold=True,
                            italic=True,
                            underline=True,
                            strikethrough=True,
                            color="#90C208",
                            link_url="https://example.com",
                        ),
                        TextRun("code", inline_code=True),
                    ]
                )
            ]
        )
        inline = canonical_document(payload["document"])[0]["text"]["inlineElements"]
        self.assertEqual(
            inline[0],
            {
                "kind": "text",
                "text": {"text": "link"},
                "bold": True,
                "italic": True,
                "underline": True,
                "strikeThrough": True,
                "color": "#90C208",
            },
        )
        self.assertIn("color", inline[1])

    async def test_images_in_nested_content_and_cover_upload(self) -> None:
        self.detail["item"]["coverImageId"] = "old-original"
        self.detail["item"]["cover"] = {"id": "old-cropped"}
        self.detail["item"]["imageList"] = [{"id": "old-original"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.webp"
            path.write_bytes(b"mock image; upload is stubbed")
            self.client.upload_image.return_value = UploadedImage(
                url="https://example.com/image.webp",
                width=100,
                height=50,
                size=12,
                image_id="uploaded-image",
            )
            self.publisher = SklandPublisher(
                self.client, SklandPublishConfig(item_id="6411493", cover_path=path)
            )
            payload = await self.publish_blocks(
                [
                    OrderedList(
                        [ListItem([ImageBlock(path, caption="caption"), Divider()])]
                    )
                ]
            )
        tree = canonical_document(payload["document"])
        self.assertEqual(tree[0]["image"]["id"], payload["coverImageId"])
        children = tree[1]["list"]["items"][0]
        self.assertEqual(children[0]["image"]["id"], "uploaded-image")
        self.assertEqual(children[0]["image"]["description"], "caption")
        self.assertEqual(children[1]["horizontalLine"], {"kind": "4"})
        self.assertEqual(payload["coverImageId"], "uploaded-image")
        self.assertEqual(payload["cover"], {})
        self.assertEqual(payload["imageList"], [])
        self.assertEqual(payload["videoList"], [])
        self.assertEqual(self.client.upload_image.await_count, 2)

    async def test_failed_or_missing_image_cannot_submit_partial_article(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.png"
            with self.assertRaises(FileNotFoundError):
                await self.publish_blocks([ImageBlock(path)])
            path.write_bytes(b"mock image")
            self.client.upload_image.side_effect = RuntimeError("upload failed")
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                await self.publish_blocks([ImageBlock(path)])
        self.client.update_item.assert_not_awaited()

    async def test_unknown_content_cannot_silently_disappear(self) -> None:
        for block in (Block(), Paragraph([InlineElement()])):
            with self.subTest(block=block), self.assertRaises(ValueError):
                await self.publish_blocks([block])
        self.client.update_item.assert_not_awaited()

    async def test_draft_defaults_remain_unchanged(self) -> None:
        publisher = SklandPublisher(self.client, SklandPublishConfig())
        draft = await publisher._convert_document(
            Document("Draft", [], None), dry_run=True
        )
        self.assertEqual((draft["model"]["gameId"], draft["model"]["cateId"]), (1, 4))

    async def test_markdown_to_edit_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "article.md"
            path.write_text(
                "# Title\n\n**bold** and ~~deleted~~\n\n> quote\n\n"
                "1. parent\n   - child\n     1. grandchild\n",
                encoding="utf-8",
            )
            doc = await MarkdownConverter(path).convert()
        await self.publisher.publish(doc)
        payload = self.client.update_item.call_args.args[0]
        tree = canonical_document(payload["document"])
        self.assertEqual(payload["title"], "Title")
        self.assertEqual(tree[0]["text"]["kind"], "heading1")
        inline = tree[1]["text"]["inlineElements"]
        self.assertTrue(inline[0]["bold"])
        self.assertTrue(inline[-1]["strikeThrough"])
        self.assertEqual(tree[2]["kind"], "quote")
        outer_list = tree[3]["list"]
        self.assertEqual(outer_list["kind"], "ordered")
        child_list = outer_list["items"][0][1]["list"]
        self.assertEqual(child_list["kind"], "unordered")
        grandchild_list = child_list["items"][0][1]["list"]
        self.assertEqual(grandchild_list["kind"], "ordered")
        self.assertEqual(
            grandchild_list["items"][0][0]["text"]["inlineElements"][0]["text"]["text"],
            "grandchild",
        )

    def test_cli_distinguishes_omitted_and_explicit_categories(self) -> None:
        parser = ArgumentParser()
        _add_skland_options(parser)
        args = parser.parse_args(["--item-id", "6411493"])
        self.assertIsNone(args.game_id)
        self.assertIsNone(args.cate_id)
        args = parser.parse_args(["--game-id", "1", "--cate-id", "4"])
        self.assertEqual((args.game_id, args.cate_id), (1, 4))


if __name__ == "__main__":
    unittest.main()
