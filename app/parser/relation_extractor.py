import re
from typing import List, Dict, Any
from app.core.id_utils import normalize_doc_id, normalize_article_id

class RelationExtractor:
    """
    Trích xuất quan hệ giữa các văn bản và điều khoản:
    1. GUIDES: Văn bản hướng dẫn thi hành (từ phần 'Căn cứ...')
    2. REFERENCES: Tham chiếu chéo giữa các Điều luật
    3. AMENDS / REPLACES: Sửa đổi, thay thế, bãi bỏ văn bản hoặc điều khoản cũ
    """

    @classmethod
    def extract_guides_relations(cls, doc_id: str, text: str) -> List[Dict[str, Any]]:
        """
        Trích xuất các văn bản cấp trên mà văn bản này hướng dẫn/căn cứ.
        Vùng 'Căn cứ Luật số...; Căn cứ Nghị định số...'
        """
        relations = []
        # Lấy đoạn đầu văn bản trước Điều 1
        intro_match = re.search(r'(.*?)(?=\b(?:Điều|ĐIỀU)\s+1\b)', text, re.DOTALL | re.IGNORECASE)
        intro_text = intro_match.group(1) if intro_match else text[:3000]
        
        # Bắt các mẫu: Căn cứ Luật số...; Căn cứ Nghị định số...
        pattern = re.compile(r'Căn cứ\s+([^;\.\n]+(?:(?:số|Số)\s*([0-9]+/[0-9]+/([A-Za-z0-9Đđ\-_]+))|[^\n;\.]+))', re.IGNORECASE)
        
        for m in pattern.finditer(intro_text):
            line = m.group(0)
            doc_symbol_m = re.search(r'([0-9]+/[0-9]+/([A-Za-z0-9Đđ\-_]+))', line)
            if doc_symbol_m:
                target_symbol = doc_symbol_m.group(1)
                target_doc_id = normalize_doc_id(target_symbol)
                if target_doc_id != doc_id:
                    relations.append({
                        "source_id": doc_id,
                        "target_id": target_doc_id,
                        "rel_type": "GUIDES",
                        "details": f"Hướng dẫn/Quy định chi tiết thi hành {target_symbol}"
                    })
        return relations

    @classmethod
    def extract_article_references(cls, doc_id: str, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Trích xuất tham chiếu chéo trong nội dung từng Điều:
        - Tham chiếu nội bộ: 'tại Điều 5', 'khoản 2 Điều 10'
        - Tham chiếu ngoại bộ: 'Điều 12 Nghị định số 100/2019/NĐ-CP'
        """
        relations = []
        
        for art in articles:
            source_art_id = art["article_id"]
            content = art["content"]
            
            # 1. Tham chiếu ngoại bộ kèm số hiệu văn bản
            # VD: "theo quy định tại Điều 15 Nghị định số 100/2019/NĐ-CP"
            ext_pattern = re.compile(
                r'(?:khoản\s+(\d+)\s+)?(?:Điều|điều)\s+(\d+)[^\.\n;]*?(?:Nghị định|Luật|Thông tư)[^\.\n;]*?(?:số|Số)\s*([0-9]+/[0-9]+/([A-Za-z0-9Đđ\-_]+))',
                re.IGNORECASE
            )
            for m in ext_pattern.finditer(content):
                clause_num = m.group(1)
                target_art_num = m.group(2)
                target_doc_sym = m.group(3)
                target_doc_id = normalize_doc_id(target_doc_sym)
                target_art_id = normalize_article_id(target_doc_id, target_art_num)
                
                relations.append({
                    "source_id": source_art_id,
                    "target_id": target_art_id,
                    "rel_type": "REFERENCES",
                    "details": f"Tham chiếu Khoản {clause_num} Điều {target_art_num} {target_doc_sym}" if clause_num else f"Tham chiếu Điều {target_art_num} {target_doc_sym}"
                })

            # 2. Tham chiếu nội bộ: "tại Điều 12", "quy định tại Điều 8" (không kèm tên văn bản khác)
            int_pattern = re.compile(r'(?:tại|theo|khoản\s+\d+\s+)?(?:Điều|điều)\s+(\d+)(?!\s*/)', re.IGNORECASE)
            for m in int_pattern.finditer(content):
                target_art_num = int(m.group(1))
                if target_art_num != art["article_number"]:
                    target_art_id = normalize_article_id(doc_id, target_art_num)
                    relations.append({
                        "source_id": source_art_id,
                        "target_id": target_art_id,
                        "rel_type": "REFERENCES",
                        "details": f"Tham chiếu nội bộ Điều {target_art_num}"
                    })

        # Loại bỏ trùng lặp
        unique_relations = []
        seen = set()
        for r in relations:
            key = (r["source_id"], r["target_id"], r["rel_type"])
            if key not in seen:
                seen.add(key)
                unique_relations.append(r)
                
        return unique_relations

    @classmethod
    def extract_amendment_relations(cls, doc_id: str, parsed_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Trích xuất quan hệ Sửa đổi, Bổ sung, Thay thế, Bãi bỏ:
        - Quét các Điều có tiêu đề 'Sửa đổi, bổ sung...', 'Hiệu lực thi hành', 'Bãi bỏ...'
        - Bắt câu: 'Nghị định này thay thế Nghị định số...'
        - Bắt câu: 'Bãi bỏ Điều X Nghị định số...'
        """
        relations = []
        text = parsed_doc["raw_text"]
        meta = parsed_doc["metadata"]
        eff_date = meta.get("effective_date", "")

        # 1. Thay thế toàn văn văn bản:
        # VD: "Nghị định này thay thế Nghị định số 100/2019/NĐ-CP"
        replace_pattern = re.compile(r'(?:thay thế|bãi bỏ)(?: toàn bộ)?\s+(?:Nghị định|Luật|Thông tư|Quyết định)[^\.\n;]*?(?:số|Số)\s*([0-9]+/[0-9]+/([A-Za-z0-9Đđ\-_]+))', re.IGNORECASE)
        for m in replace_pattern.finditer(text):
            target_symbol = m.group(1)
            target_doc_id = normalize_doc_id(target_symbol)
            if target_doc_id != doc_id:
                relations.append({
                    "source_id": doc_id,
                    "target_id": target_doc_id,
                    "rel_type": "REPLACES",
                    "details": f"Thay thế văn bản {target_symbol} từ ngày {eff_date}"
                })

        # 2. Sửa đổi, bổ sung từng Điều cụ thể:
        for art in parsed_doc["articles"]:
            art_content = art["content"]
            # Bắt mẫu: "Sửa đổi, bổ sung Điều X của Nghị định số Y"
            amend_match = re.search(
                r'(?:Sửa đổi|bổ sung|bãi bỏ)\s+(?:khoản\s+\d+\s+)?(?:Điều|điều)\s+(\d+)\s+(?:của|Nghị định|Luật|Thông tư)[^\.\n;]*?(?:số|Số)\s*([0-9]+/[0-9]+/([A-Za-z0-9Đđ\-_]+))',
                art_content,
                re.IGNORECASE
            )
            if amend_match:
                old_art_num = amend_match.group(1)
                old_doc_sym = amend_match.group(2)
                old_doc_id = normalize_doc_id(old_doc_sym)
                old_art_id = normalize_article_id(old_doc_id, old_art_num)
                
                relations.append({
                    "source_id": art["article_id"],
                    "target_id": old_art_id,
                    "rel_type": "AMENDS",
                    "details": f"Sửa đổi Điều {old_art_num} của {old_doc_sym} từ {eff_date}"
                })

        return relations
