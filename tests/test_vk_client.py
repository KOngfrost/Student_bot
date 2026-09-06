"""Тесты единой точки отправки VK-сообщений (core.vk_client)."""

from unittest.mock import AsyncMock, MagicMock, patch

from core.vk_client import send_vk_message


async def test_send_vk_message_zero_peer_returns_false():
    """vk_id=0 — сообщение не отправляется."""
    assert await send_vk_message(0, "text") is False


async def test_send_vk_message_no_token_returns_false(monkeypatch):
    """Без токена бота возвращает False без HTTP-вызова."""
    import core.vk_client as vk_client

    monkeypatch.setattr(vk_client.settings, "VK_BOT_TOKEN", None)
    assert await send_vk_message(123, "text") is False


async def test_send_vk_message_success_posts_to_api():
    """Успешный HTTP-ответ без error подтверждает отправку."""
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(return_value={"response": 1})

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_response
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch("core.vk_client.httpx.AsyncClient", return_value=fake_client):
        ok = await send_vk_message(456, "Привет")

    assert ok is True
    # Проверяем, что обращение ушло на правильный endpoint с peer_id
    call_kwargs = fake_client.post.call_args.kwargs
    assert call_kwargs["data"]["peer_id"] == 456
    assert call_kwargs["data"]["message"] == "Привет"


async def test_send_vk_message_api_error_returns_false():
    """Ответ VK с полем error трактуется как неудача (не исключение)."""
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(
        return_value={"error": {"error_code": 902, "error_msg": "Капча"}}
    )

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_response
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch("core.vk_client.httpx.AsyncClient", return_value=fake_client):
        ok = await send_vk_message(789, "text")

    assert ok is False


async def test_send_vk_message_http_error_returns_false():
    """Исключение HTTP — неудача без проброса."""
    import httpx

    fake_client = AsyncMock()
    fake_client.post.side_effect = httpx.ConnectError("network down")
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch("core.vk_client.httpx.AsyncClient", return_value=fake_client):
        ok = await send_vk_message(111, "text")

    assert ok is False
