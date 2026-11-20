import re
from typing import List, Dict, Any, Optional
from app.core.id_utils import normalize_doc_id, normalize_article_id, normalize_clause_id

class LegalParser:
    """
    Parser quy chuẩn cho văn bản quy phạm pháp luật Việt Nam.
    Tách cấu trúc phân cấp: Văn bản -> Chương -> Điều -> Khoản -> Điểm.
    """
    
    @staticmethod
    def extract_metadata(text: str) -> Dict[str, Any]:
        """Trích xuất thông tin tổng quan của văn bản."""
        meta = {
            "doc_symbol": "",
            "doc_id": "",
            "doc_type": "Văn bản",
            "title": "",
            "issue_date": "",
            "effective_date": "",
            "domain": "chung"
        }
        
        # 1. Bắt số hiệu văn bản (vd: Số: 168/2024/NĐ-CP hoặc 100/2019/NĐ-CP)
        symbol_match = re.search(r'(?:Số|Số:)\s*([0-9]+/[0-9]+/([A-Za-z0-9Đđ\-_]+))', text, re.IGNORECASE)
        if symbol_match:
            meta["doc_symbol"] = symbol_match.group(1).strip()
            meta["doc_id"] = normalize_doc_id(meta["doc_symbol"])
            
            # Phân loại loại văn bản
            upper_sym = meta["doc_symbol"].upper()
            if "ND-CP" in upper_sym or "NĐ-CP" in upper_sym:
                meta["doc_type"] = "Nghị định"
            elif "TT-" in upper_sym or "TT/" in upper_sym:
                meta["doc_type"] = "Thông tư"
            elif "QH" in upper_sym:
                meta["doc_type"] = "Luật"
            elif "QD-" in upper_sym or "QĐ-" in upper_sym:
                meta["doc_type"] = "Quyết định"
                
        # 2. Bắt ngày ban hành: ngày ... tháng ... năm ...
        issue_match = re.search(r'ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})', text, re.IGNORECASE)
        if issue_match:
            d, m, y = issue_match.groups()
            meta["issue_date"] = f"{y}-{int(m):02d}-{int(d):02d}"
            
        # 3. Bắt ngày có hiệu lực: có hiệu lực từ/kể từ ngày ...
        eff_match = re.search(r'(?:có hiệu lực(?: thi hành)?(?: từ| kể từ)?)\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})', text, re.IGNORECASE)
        if eff_match:
            d, m, y = eff_match.groups()
            meta["effective_date"] = f"{y}-{int(m):02d}-{int(d):02d}"
        else:
            meta["effective_date"] = meta["issue_date"] # Fallback

        # 4. Trích xuất trích yếu / tiêu đề văn bản
        # Thường nằm sau NGHỊ ĐỊNH / QUYẾT ĐỊNH / LUẬT
        title_match = re.search(r'(?:NGHỊ ĐỊNH|THÔNG TƯ|QUYẾT ĐỊNH|LUẬT)\s*\n+([^\n]+(?:\n+[^\n]+){1,3}?)(?=\n+\s*(?:Căn cứ|Điều 1|\bCHƯƠNG\b))', text, re.IGNORECASE)
        if title_match:
            meta["title"] = " ".join(title_match.group(1).split())[:450]
        else:
            first_lines = [l.strip() for l in text.split("\n") if l.strip()][:5]
            meta["title"] = (" - ".join(first_lines) if first_lines else "Văn bản quy phạm pháp luật")[:450]
            
        if not meta["title"]:
            meta["title"] = "Văn bản pháp luật"
            
        # Xác định domain nếu có từ khóa
        lower_all = text.lower()
        if any(w in lower_all for w in ["giao thông", "đường bộ", "xe mô tô", "xe ô tô", "bằng lái"]):
            meta["domain"] = "giao_thong"
        elif any(w in lower_all for w in ["lao động", "tiền lương", "bảo hiểm xã hội", "hợp đồng lao động"]):
            meta["domain"] = "lao_dong"
        elif any(w in lower_all for w in ["doanh nghiệp", "kinh doanh", "đầu tư", "thuế", "hóa đơn"]):
            meta["domain"] = "doanh_nghiep"
        elif any(w in lower_all for w in ["đất đai", "nhà ở", "bất động sản", "sổ đỏ"]):
            meta["domain"] = "dat_dai"

        return meta

    @classmethod
    def parse_document(cls, text: str, doc_symbol_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Phân tách toàn bộ văn bản thành cây cấu trúc:
        Document -> Chapters -> Articles -> Clauses.
        """
        meta = cls.extract_metadata(text)
        if doc_symbol_override:
            meta["doc_symbol"] = doc_symbol_override
            meta["doc_id"] = normalize_doc_id(doc_symbol_override)
            
        if not meta["doc_id"]:
            # Fallback nếu không bắt được số hiệu
            meta["doc_id"] = "DOC_UNKNOWN"
            meta["doc_symbol"] = "Chưa rõ số hiệu"

        doc_id = meta["doc_id"]
        
        # Tách theo Chương nếu có
        # Regex bắt "Chương I...", "CHƯƠNG II:..."
        chapter_pattern = re.compile(r'^\s*(?:Chương|CHƯƠNG)\s+([IVXLCDM0-9]+)[:\.\s\-]*([^\n]*)', re.MULTILINE)
        
        # Regex bắt Điều: "Điều 1.", "Điều 7:", "Điều 15 -"
        article_pattern = re.compile(r'^\s*(?:Điều|ĐIỀU)\s+(\d+)\s*[\.\:\-]?\s*([^\n]*)', re.MULTILINE)
        
        article_matches = list(article_pattern.finditer(text))
        
        articles_by_num: Dict[int, Dict[str, Any]] = {}
        validation_warnings = []
        last_article_num = 0
        
        for i, match in enumerate(article_matches):
            art_num = int(match.group(1))
            art_title = match.group(2).strip()
            start_pos = match.start()
            end_pos = article_matches[i + 1].start() if i + 1 < len(article_matches) else len(text)
            
            raw_article_text = text[start_pos:end_pos].strip()
            article_id = normalize_article_id(doc_id, art_num)

            # Nếu số Điều này đã xuất hiện (do mục lục đầu file hoặc điều khoản trích dẫn ở cuối):
            # So sánh độ dài: giữ lại bản có nội dung đầy đủ nhất (bản chính văn)
            if art_num in articles_by_num:
                existing_art = articles_by_num[art_num]
                if len(raw_article_text) <= len(existing_art["content"]):
                    # Bản cũ dài hơn hoặc bằng -> bỏ qua dòng lặp ngắn
                    continue
            
            # Kiểm tra validation gate: nhảy cóc số Điều
            if last_article_num > 0 and art_num != last_article_num + 1:
                validation_warnings.append(f"Cảnh báo thứ tự: Nhảy cóc từ Điều {last_article_num} sang Điều {art_num}")
            last_article_num = art_num
            
            # Tìm xem Điều này thuộc Chương nào bằng cách quét ngược từ start_pos
            current_chapter = "Quy định chung"
            preceding_text = text[:start_pos]
            chap_matches = list(chapter_pattern.finditer(preceding_text))
            if chap_matches:
                last_chap = chap_matches[-1]
                current_chapter = f"Chương {last_chap.group(1)}: {last_chap.group(2).strip()}"

            # Tách Khoản trong Điều
            # Regex bắt Khoản: "1. Phạt...", "2. Người có thẩm quyền..."
            clause_pattern = re.compile(r'^\s*(\d+)\.\s+([^\n]+(?:\n+(?!\s*\d+\.\s+)[^\n]+)*)', re.MULTILINE)
            clause_matches = list(clause_pattern.finditer(raw_article_text))
            
            clauses = []
            seen_clause_nums = set()
            if clause_matches:
                for c_match in clause_matches:
                    c_num = int(c_match.group(1))
                    if c_num in seen_clause_nums:
                        continue
                    seen_clause_nums.add(c_num)
                    c_content = c_match.group(0).strip()
                    c_id = normalize_clause_id(article_id, c_num)
                    clauses.append({
                        "clause_id": c_id,
                        "clause_number": c_num,
                        "content": c_content
                    })
            else:
                # Nếu không đánh số khoản (điều ngắn 1 khoản)
                clauses.append({
                    "clause_id": normalize_clause_id(article_id, 1),
                    "clause_number": 1,
                    "content": raw_article_text
                })

            articles_by_num[art_num] = {
                "article_id": article_id,
                "doc_id": doc_id,
                "chapter_title": current_chapter,
                "article_number": art_num,
                "title": art_title or f"Điều {art_num}",
                "content": raw_article_text,
                "status": "active",
                "effective_date": meta["effective_date"],
                "clauses": clauses
            }

        articles = sorted(list(articles_by_num.values()), key=lambda a: a["article_number"])

        if not articles:
            # Fallback nếu văn bản không dùng cấu trúc "Điều 1..."
            articles.append({
                "article_id": f"{doc_id}_DIEU_1",
                "doc_id": doc_id,
                "chapter_title": "Quy định chung",
                "article_number": 1,
                "title": (meta.get("title") or "Nội dung quy định")[:100],
                "content": text.strip()[:10000],
                "status": "active",
                "effective_date": meta["effective_date"],
                "clauses": [{
                    "clause_id": f"{doc_id}_DIEU_1_KHOAN_1",
                    "article_id": f"{doc_id}_DIEU_1",
                    "clause_number": 1,
                    "content": text.strip()[:10000]
                }]
            })

        return {
            "metadata": meta,
            "articles": articles,
            "validation_warnings": validation_warnings,
            "raw_text": text
        }

    @classmethod
    def generate_qdrant_chunks(cls, parsed_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Structure-aware Chunking & Contextual Header Injection:
        - Nếu 1 Điều <= 1500 ký tự (~500 tokens): Giữ nguyên Điều làm 1 chunk.
        - Nếu 1 Điều > 1500 ký tự: Tách nhỏ theo từng Khoản.
        - Ghép Contextual Header vào đầu chunk.
        """
        meta = parsed_doc["metadata"]
        chunks = []
        
        for art in parsed_doc["articles"]:
            doc_symbol = meta["doc_symbol"]
            eff_date = art["effective_date"] or meta["effective_date"] or "Hiện hành"
            chap = art["chapter_title"]
            art_num = art["article_number"]
            art_title = art["title"]
            
            # Header cố định
            header_prefix = f"[{doc_symbol} | Hiệu lực: {eff_date} | {chap} | Điều {art_num}: {art_title}]"
            
            # Nếu điều ngắn
            if len(art["content"]) <= 1500 or len(art["clauses"]) <= 1:
                chunk_text = f"{header_prefix}\n{art['content']}"
                chunks.append({
                    "article_id": art["article_id"],
                    "doc_id": art["doc_id"],
                    "clause_id": None,
                    "clause_number": None,
                    "domain": meta["domain"],
                    "status": art["status"],
                    "effective_date": eff_date,
                    "chunk_text": chunk_text
                })
            else:
                # Điều dài: Tách theo Khoản
                for cl in art["clauses"]:
                    c_header = f"[{doc_symbol} | Hiệu lực: {eff_date} | {chap} | Điều {art_num}: {art_title} | Khoản {cl['clause_number']}]"
                    chunk_text = f"{c_header}\n{cl['content']}"
                    chunks.append({
                        "article_id": art["article_id"],
                        "doc_id": art["doc_id"],
                        "clause_id": cl["clause_id"],
                        "clause_number": cl["clause_number"],
                        "domain": meta["domain"],
                        "status": art["status"],
                        "effective_date": eff_date,
                        "chunk_text": chunk_text
                    })
                    
        return chunks
