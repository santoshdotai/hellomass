import io

from loguru import logger

from src.security.redaction import (build_rtsp_url, mask_url, redact_mapping, redact_text, safe_filename, split_credentials,
                                    strip_credentials, url_has_credentials)


def test_mask_url_hides_user_and_password():
    assert mask_url("rtsp://admin:S3cret!@10.0.0.5:554/Streaming/Channels/101") == "rtsp://***:***@10.0.0.5:554/Streaming/Channels/101"
    assert mask_url("rtsp://10.0.0.5/ch1") == "rtsp://10.0.0.5/ch1"
    assert mask_url("") == ""


def test_mask_url_hides_query_tokens():
    assert mask_url("https://nvr.local/api/stream?token=abc123&ch=1") == "https://nvr.local/api/stream?token=***&ch=1"


def test_redact_text_covers_free_text():
    msg = "connect failed for rtsp://user:pa55@cam/live password=hunter2 token: xyz"
    out = redact_text(msg)
    assert "pa55" not in out and "hunter2" not in out and "xyz" not in out
    assert "rtsp://***:***@cam/live" in out


def test_redact_mapping_recurses():
    data = {"url": "rtsp://a:b@h/x", "password": "p", "nested": [{"api_key": "k", "name": "ok"}]}
    out = redact_mapping(data)
    assert out["url"] == "rtsp://***:***@h/x" and out["password"] == "***" and out["nested"][0]["api_key"] == "***"
    assert out["nested"][0]["name"] == "ok"


def test_build_and_split_credentials():
    url = build_rtsp_url("rtsp://cam:554/ch1", "ad min", "p@ss:word")
    assert url == "rtsp://ad%20min:p%40ss%3Aword@cam:554/ch1"
    assert url_has_credentials(url) and not url_has_credentials("rtsp://cam/ch1")
    assert strip_credentials(url) == "rtsp://cam:554/ch1"
    base, user, pw = split_credentials(url)
    assert base == "rtsp://cam:554/ch1" and user == "ad min" and pw == "p@ss:word"
    assert build_rtsp_url("rtsp://x:y@cam/ch1") == "rtsp://x:y@cam/ch1"


def test_safe_filename():
    assert safe_filename("../EV-1 intrusion/../x.jpg") == "EV-1_intrusion_.._x.jpg"
    assert "/" not in safe_filename("a/b\\c")


def test_logging_sink_redacts_credentials():
    from src.monitoring.logging_config import _redacting_patcher
    buf = io.StringIO()
    logger.remove()
    logger.configure(patcher=_redacting_patcher)
    logger.add(buf, format="{message}")
    logger.warning("opening rtsp://root:TopSecret@192.168.9.9/live")
    logger.remove()
    assert "TopSecret" not in buf.getvalue() and "rtsp://***:***@192.168.9.9/live" in buf.getvalue()


def test_rtsp_source_repr_and_masked_url_never_leak():
    from src.sources.rtsp import RTSPSource
    src = RTSPSource("rtsp://cam.local:554/ch1", username="viewer", password="Hidden1")
    assert "Hidden1" not in repr(src) and "Hidden1" not in str(src) and "Hidden1" not in src.masked_url
    assert src.masked_url == "rtsp://***:***@cam.local:554/ch1"
    assert "Hidden1" not in str(src.describe())
