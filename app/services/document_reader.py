import io
from typing import Optional

def extract_text_from_file(filename: str, content_bytes: bytes) -> str:
    """
    Trích xuất toàn văn bản từ các định dạng file: .txt, .pdf, .docx
    """
    ext = filename.lower().split(".")[-1]
    
    if ext == "txt":
        try:
            return content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content_bytes.decode("utf-16")
            except UnicodeDecodeError:
                return content_bytes.decode("latin-1", errors="ignore")
                
    elif ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            full_text = "\n\n".join(pages_text)
            if not full_text.strip():
                raise ValueError("Không thể trích xuất văn bản từ file PDF (có thể là file scan dạng ảnh).")
            return full_text
        except Exception as e:
            raise ValueError(f"Lỗi khi đọc file PDF: {str(e)}")
            
    elif ext in ["docx", "doc"]:
        try:
            import docx
            doc = docx.Document(io.BytesIO(content_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                    if row_text:
                        paragraphs.append(row_text)
            full_text = "\n".join(paragraphs)
            if not full_text.strip():
                raise ValueError("File DOCX không chứa văn bản hợp lệ.")
            return full_text
        except Exception as e:
            raise ValueError(f"Lỗi khi đọc file Word (.docx): {str(e)}")
            
    else:
        raise ValueError(f"Định dạng file .{ext} chưa được hỗ trợ. Vui lòng tải lên file .txt, .pdf hoặc .docx")
