import sys
import unittest
from pathlib import Path
from io import BytesIO
from werkzeug.datastructures import FileStorage
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lyrics_validation import validate_lyrics_upload,MAX_LYRICS_BYTES

class LyricsValidationTests(unittest.TestCase):
    def validate(self,text,suffix='.ttml'):
        upload=FileStorage(stream=BytesIO(text),filename='lyrics'+suffix)
        result=validate_lyrics_upload(upload,suffix)
        self.assertEqual(upload.stream.tell(),0)
        return result[0]
    def test_valid_utf8_text_and_ttml(self):
        self.assertTrue(self.validate('Текст песни'.encode(),'.txt'))
        self.assertTrue(self.validate(b'<tt xmlns="http://www.w3.org/ns/ttml"><body><div><p begin="00:00:01.000" end="00:00:02.000">Hello &amp; world</p></div></body></tt>'))
    def test_media_upload_routes_apply_content_validation(self):
        import api
        upload=FileStorage(stream=BytesIO(b'<tt><body><div><p begin="1s" end="2s">Text</p></div></body></tt>'),filename='lyrics.ttml',content_type='application/ttml+xml')
        self.assertTrue(api.validate_upload_file(upload,api.MEDIA_KIND_FILE_TYPES['lyrics'])[0])
        self.assertEqual(upload.stream.tell(),0)
        invalid=FileStorage(stream=BytesIO(b'<svg>not lyrics</svg>'),filename='lyrics.xml',content_type='application/xml')
        self.assertFalse(api.validate_upload_file(invalid,api.MEDIA_KIND_FILE_TYPES['lyrics'])[0])
        self.assertFalse(api.validate_upload_file(upload,api.MEDIA_KIND_FILE_TYPES['contract'])[0])

    def test_reject_entities_other_xml_and_invalid_files(self):
        for raw in [b'',b'\x00\x01',b'<svg><p>text</p></svg>',b'<tt><body/></tt>',b'<tt><p>text</tt>',b'<!DOCTYPE tt [<!ENTITY secret SYSTEM "file:///etc/passwd">]><tt><p>&secret;</p></tt>',b'x'*(MAX_LYRICS_BYTES+1)]:
            with self.subTest(size=len(raw)):self.assertFalse(self.validate(raw))
        self.assertFalse(self.validate(b'\xff','.txt'))
if __name__=='__main__':unittest.main()
