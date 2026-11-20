import re
import unicodedata

def remove_vietnamese_diacritics(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để tạo slug ID chuẩn hóa."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.replace('đ', 'd').replace('Đ', 'D')
    return text

def normalize_doc_id(doc_symbol: str) -> str:
    """
    Chuẩn hóa số hiệu văn bản thành doc_id thống nhất.
    VD:
      "168/2024/NĐ-CP" -> "168_2024_NDCP"
      "100/2019/QH14" -> "100_2019_QH14"
      "Nghị định 123/2021/NĐ-CP" -> "123_2021_NDCP"
      "Luật số 45/2019/QH14" -> "45_2019_QH14"
    """
    # Lấy phần số hiệu văn bản (vd: 168/2024/NĐ-CP)
    match = re.search(r'(\d+)/(\d+)/([A-Za-z0-9Đđ\-_]+)', doc_symbol)
    if match:
        num, year, org = match.groups()
        org_clean = remove_vietnamese_diacritics(org).upper()
        org_clean = re.sub(r'[^A-Z0-9]', '', org_clean)
        return f"{num}_{year}_{org_clean}"
    
    # Trường hợp số hiệu dạng rút gọn hoặc đặc thù
    clean = remove_vietnamese_diacritics(doc_symbol).upper()
    clean = re.sub(r'[^A-Z0-9]', '_', clean)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean

def normalize_article_id(doc_id: str, article_num: int | str) -> str:
    """
    Chuẩn hóa ID của Điều luật:
    VD: doc_id = "168_2024_NDCP", article_num = 7 -> "168_2024_NDCP_DIEU_7"
    """
    clean_num = str(article_num).strip().upper()
    clean_num = re.sub(r'[^0-9A-Z]', '', clean_num)
    return f"{doc_id}_DIEU_{clean_num}"

def normalize_clause_id(article_id: str, clause_num: int | str) -> str:
    """
    Chuẩn hóa ID của Khoản:
    VD: article_id = "168_2024_NDCP_DIEU_7", clause_num = 2 -> "168_2024_NDCP_DIEU_7_KHOAN_2"
    """
    clean_num = str(clause_num).strip()
    return f"{article_id}_KHOAN_{clean_num}"
