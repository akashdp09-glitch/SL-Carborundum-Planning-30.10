"""SYNTHETIC QR round trips reproduce missing optional-backend failure."""
import builtins
from io import BytesIO
import cv2
import numpy as np
import pytest
from suite.qr_png import make,png_bytes


@pytest.mark.parametrize('payload',['SLWO:SYNTHETIC-QR-59','http://192.0.2.10:8000/scan','https://example.invalid/mobile/audit/SYNTHETIC-59'])
def test_png_decodes_when_optional_qrcode_pil_backend_is_missing(monkeypatch,payload,tmp_path):
    original=builtins.__import__
    def no_optional(name,*a,**kw):
        if name=='qrcode.image.pil' or name=='PIL' or name.startswith('PIL.'):
            raise ModuleNotFoundError('SYNTHETIC missing optional backend: '+name)
        return original(name,*a,**kw)
    with monkeypatch.context() as m:
        m.setattr(builtins,'__import__',no_optional)
        out=BytesIO();make(payload).save(out,format='PNG')
        path=tmp_path/'SYNTHETIC.png';make(payload).save(path)
    assert path.read_bytes()==out.getvalue()
    image=cv2.imdecode(np.frombuffer(out.getvalue(),np.uint8),cv2.IMREAD_GRAYSCALE)
    decoded,points,_=cv2.QRCodeDetector().detectAndDecode(image)
    assert decoded==payload and points is not None


def test_invalid_png_parameters_fail_explicitly():
    with pytest.raises(ValueError):png_bytes('SYNTHETIC',border=0)
    with pytest.raises(ValueError):png_bytes('SYNTHETIC',box_size=0)
