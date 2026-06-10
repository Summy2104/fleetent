"""File attachment contract in the normalizer: FileAttachment + pickers."""

from fleetent.im_gateway.normalizer import (
    FileAttachment,
    _file_attachments,
    _image_attachments,
)


def test_file_attachment_defaults():
    fa = FileAttachment(data=b"x", mime="application/pdf", filename="a.pdf")
    assert fa.data == b"x"
    assert fa.mime == "application/pdf"
    assert fa.filename == "a.pdf"
    assert fa.note == ""


def test_file_attachments_picks_file_items_including_failed():
    img = (b"img", "image/png")
    ok = FileAttachment(data=b"x", mime="application/pdf", filename="a.pdf")
    failed = FileAttachment(data=None, mime="text/csv", filename="b.csv", note="超过大小上限")
    picked = _file_attachments([img, ok, failed, "junk", (b"y", "image/jpeg")])
    assert picked == [ok, failed]


def test_image_attachments_ignores_file_items():
    img = (b"img", "image/png")
    fa = FileAttachment(data=b"x", mime="application/pdf", filename="a.pdf")
    images = _image_attachments([img, fa])
    assert images == [(b"img", "image/png")]
