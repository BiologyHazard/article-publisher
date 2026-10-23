from typing import TypedDict


class InternalTenantAccessTokenRequest(TypedDict):
    """
    自建应用获取 `tenant_access_token` 的 API 请求数据结构。

    文档：https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal

    调用方式：POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal

    ```json
    {
        "app_id": "cli_slkdjalasdkjasd",
        "app_secret": "dskLLdkasdjlasdKK"
    }
    ```
    """

    app_id: str
    app_secret: str


class InternalTenantAccessTokenResponse(TypedDict):
    """
    自建应用获取 `tenant_access_token` 的 API 响应数据结构。

    文档：https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal

    调用方式：POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal

    ```json
    {
        "code": 0,
        "msg": "ok",
        "tenant_access_token": "t-caecc734c2e3328a62489fe0648c4b98779515d3",
        "expire": 7200
    }
    ```
    """

    code: int
    msg: str
    tenant_access_token: str
    expire: int
