"""Bounded text/TTML validation without executing XML declarations or entities."""
import re
import xml.etree.ElementTree as ET

MAX_LYRICS_BYTES = 5 * 1024 * 1024


def validate_lyrics_upload(upload, suffix):
    raw = upload.stream.read(MAX_LYRICS_BYTES + 1)
    upload.stream.seek(0)
    if not raw or len(raw) > MAX_LYRICS_BYTES:
        return False, 'Текстовый файл пустой или превышает 5 МБ.'
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: return False, 'Сохраните текстовый файл в UTF-8.'
    if '\x00' in text: return False, 'Ожидается текстовый файл.'
    if suffix == '.txt': return (True, None) if text.strip() else (False, 'Текст пустой.')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I):
        return False, 'Объявления DTD и сущностей XML не разрешены.'
    try: root = ET.fromstring(text)
    except ET.ParseError: return False, 'Некорректный XML / TTML.'
    if root.tag not in {'tt', '{http://www.w3.org/ns/ttml}tt'}:
        return False, 'Ожидается документ TTML с корневым элементом tt.'
    paragraphs = [node for node in root.iter() if node.tag in {'p', '{http://www.w3.org/ns/ttml}p'}]
    if not paragraphs or not any(''.join(node.itertext()).strip() for node in paragraphs):
        return False, 'TTML не содержит строк текста.'
    if len(paragraphs)>10000: return False, 'Слишком много строк в TTML.'
    return True, None
