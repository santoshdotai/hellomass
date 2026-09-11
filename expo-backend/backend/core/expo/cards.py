"""Business-card capture: OCR/LLM extraction of visitor cards, plus vCard/QR
payloads so a visitor can scan Souveno's card and Souveno keeps theirs.

Extraction strategy (best available wins):
  1. Anthropic vision (if LLM_API_KEY is set) — reads the photo directly.
  2. pytesseract (if installed) — local OCR, then the regex parser below.
  3. Regex parser on pasted/typed text — always available, zero dependencies.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any

from loguru import logger

from config.settings import settings

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-()]{7,}\d)")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?", re.I)
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
TITLE_WORDS = ("ceo", "cto", "coo", "cfo", "founder", "director", "manager", "head", "owner", "proprietor",
               "partner", "president", "vp", "vice president", "engineer", "executive", "sales", "purchase",
               "procurement", "md", "managing", "gm", "general manager", "lead", "officer", "chairman", "supervisor")
COMPANY_HINTS = ("pvt", "ltd", "llp", "limited", "industries", "enterprises", "traders", "corporation", "corp",
                 "inc", "co.", "company", "agencies", "polymers", "pipes", "cables", "engineering", "works",
                 "exports", "imports", "solutions", "systems", "technologies", "tech", "steels", "metals",
                 "packaging", "plastics", "electricals", "hardware", "fasteners", "distributors", "&", "and sons")


def parse_card_text(text: str) -> dict[str, Any]:
    raw_lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in raw_lines if ln]
    out: dict[str, Any] = {"name": "", "company": "", "designation": "", "email": "", "phone": "",
                           "website": "", "gstin": "", "address": "", "raw_text": text, "confidence": 0.0}
    joined = "\n".join(lines)
    if m := EMAIL_RE.search(joined):
        out["email"] = m.group(0).lower()
    if m := GSTIN_RE.search(joined.upper()):
        out["gstin"] = m.group(0)
    phones = [re.sub(r"[^\d+]", "", p) for p in PHONE_RE.findall(joined)]
    phones = [p for p in phones if 10 <= len(p.lstrip("+")) <= 13 and not GSTIN_RE.search(p)]
    if phones:
        p = phones[0]
        if len(p) == 10:
            p = "+91" + p
        elif p.startswith("91") and len(p) == 12:
            p = "+" + p
        out["phone"] = p
    for u in URL_RE.findall(joined):
        if "@" in u or re.fullmatch(r"[\d.+\-\s]+", u):
            continue
        if any(u.lower().endswith(tld) or ("." + tld + "/") in u.lower() for tld in ("com", "in", "co.in", "net", "org", "ai", "io", "biz")):
            out["website"] = u if u.startswith("http") else "https://" + u
            break

    remaining = []
    for ln in lines:
        low = ln.lower()
        if EMAIL_RE.search(ln) or PHONE_RE.search(ln) or GSTIN_RE.search(ln.upper()):
            continue
        if URL_RE.search(ln) and ("www" in low or any(low.endswith(t) for t in (".com", ".in", ".ai", ".io", ".net", ".org"))):
            continue
        remaining.append(ln)

    for ln in remaining:
        low = ln.lower()
        if not out["designation"] and any(re.search(rf"\b{re.escape(w)}\b", low) for w in TITLE_WORDS):
            out["designation"] = ln
        elif not out["company"] and any(h in low for h in COMPANY_HINTS):
            out["company"] = ln
    for ln in remaining:
        if ln in (out["designation"], out["company"]):
            continue
        words = ln.split()
        if 1 < len(words) <= 4 and all(w[:1].isupper() or w.isupper() for w in words) and not any(ch.isdigit() for ch in ln):
            out["name"] = ln
            break
    if not out["company"] and out["email"]:
        dom = out["email"].split("@")[1].split(".")[0]
        if dom not in ("gmail", "yahoo", "hotmail", "outlook", "rediffmail"):
            out["company"] = dom.capitalize()
    addr = [ln for ln in remaining if ln not in (out["name"], out["company"], out["designation"]) and
            (any(ch.isdigit() for ch in ln) or any(k in ln.lower() for k in ("road", "rd", "street", "nagar", "industrial", "area", "phase", "plot", "sector", "hyderabad", "mumbai", "pune", "delhi", "ahmedabad", "chennai", "bengaluru", "india")))]
    out["address"] = ", ".join(addr)[:300]
    filled = sum(1 for k in ("name", "company", "email", "phone") if out[k])
    out["confidence"] = round(filled / 4, 2)
    out["method"] = "regex"
    return out


def _tesseract_text(image_bytes: bytes) -> str | None:
    try:
        import io

        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        return pytesseract.image_to_string(Image.open(io.BytesIO(image_bytes)))
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.debug(f"tesseract unavailable: {exc}")
        return None


def _anthropic_extract(image_bytes: bytes, media_type: str) -> dict[str, Any] | None:
    if not settings.llm_api_key or settings.llm_provider != "anthropic":
        return None
    try:  # pragma: no cover - network
        import requests

        prompt = ("Extract the business card into JSON with keys name, company, designation, email, phone, "
                  "website, gstin, address, industry. Use empty strings when unknown. Reply with JSON only.")
        body = {
            "model": settings.llm_model,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image_bytes).decode()}},
                {"type": "text", "text": prompt}]}],
        }
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=40,
                          headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json=body)
        r.raise_for_status()
        text = "".join(part.get("text", "") for part in r.json().get("content", []))
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        data["method"] = "anthropic-vision"
        data["confidence"] = 0.9
        data.setdefault("raw_text", "")
        return data
    except Exception as exc:
        logger.warning(f"LLM card extraction failed, falling back: {exc}")
        return None


def extract_card(image_bytes: bytes | None = None, media_type: str = "image/jpeg", text: str | None = None) -> dict[str, Any]:
    if image_bytes:
        if data := _anthropic_extract(image_bytes, media_type):
            return data
        if ocr := _tesseract_text(image_bytes):
            data = parse_card_text(ocr)
            data["method"] = "tesseract+regex"
            return data
        if not text:
            return {"name": "", "company": "", "designation": "", "email": "", "phone": "", "website": "", "gstin": "",
                    "address": "", "raw_text": "", "confidence": 0.0, "method": "none",
                    "hint": "No OCR engine available: set LLM_API_KEY for vision extraction or install pytesseract. Type the card text instead."}
    return parse_card_text(text or "")


def vcard(profile: dict[str, str]) -> str:
    n = profile.get("contact_name", "")
    parts = n.split(" ", 1)
    last, first = (parts[1], parts[0]) if len(parts) == 2 else ("", n)
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"N:{last};{first};;;", f"FN:{n}", f"ORG:{profile.get('company', '')}",
             f"TITLE:{profile.get('designation', '')}", f"TEL;TYPE=CELL:{profile.get('phone', '')}",
             f"EMAIL;TYPE=WORK:{profile.get('email', '')}", f"URL:{profile.get('website', '')}",
             f"ADR;TYPE=WORK:;;{profile.get('address', '')};{profile.get('city', '')};{profile.get('state', '')};;{profile.get('country', '')}",
             f"NOTE:{profile.get('description', '')[:200]}", "END:VCARD"]
    return "\r\n".join(lines) + "\r\n"
