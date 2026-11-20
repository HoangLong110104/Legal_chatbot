import logging
from sqlalchemy.orm import Session
from app.services.ingestion import IngestionPipeline

logger = logging.getLogger(__name__)

# Mẫu 1: Nghị định 100/2019/NĐ-CP (Giao thông đường bộ)
DOC_100_2019 = """
CHÍNH PHỦ
Số: 100/2019/NĐ-CP
Hà Nội, ngày 30 tháng 12 năm 2019

NGHỊ ĐỊNH
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt

Căn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015;
Căn cứ Luật Xử lý vi phạm hành chính ngày 20 tháng 6 năm 2012;
Căn cứ Luật Giao thông đường bộ số 23/2008/QH12;
Theo đề nghị của Bộ trưởng Bộ Giao thông vận tải,
Chính phủ ban hành Nghị định quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt.

CHƯƠNG I: QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Nghị định này quy định về hành vi vi phạm hành chính, hình thức, mức xử phạt, biện pháp khắc phục hậu quả đối với từng hành vi vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt.
2. Các hành vi vi phạm hành chính trong các lĩnh vực quản lý nhà nước khác liên quan đến giao thông đường bộ và đường sắt không quy định tại Nghị định này thì áp dụng quy định tại các nghị định xử phạt vi phạm hành chính trong các lĩnh vực đó.

Điều 2. Đối tượng áp dụng
1. Cá nhân, tổ chức có hành vi vi phạm hành chính trong lĩnh vực giao thông đường bộ, đường sắt trên lãnh thổ nước Cộng hòa xã hội chủ nghĩa Việt Nam.
2. Người có thẩm quyền xử phạt và cá nhân, tổ chức có liên quan.

CHƯƠNG II: HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT

Điều 5. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường;
b) Chuyển hướng không nhường quyền đi trước cho người đi bộ.
2. Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với người điều khiển xe chuyển làn đường không đúng nơi cho phép hoặc không có tín hiệu báo trước.
3. Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng đối với người điều khiển xe thực hiện hành vi:
a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ hoặc đèn vàng);
b) Đi ngược chiều của đường một chiều, đi ngược chiều trên đường có biển Cấm đi ngược chiều.
4. Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn chưa vượt quá 50 miligam/100 mililít máu hoặc chưa vượt quá 0,25 miligam/1 lít khí thở theo quy định tại Điều 2.
5. Phạt tiền từ 16.000.000 đồng đến 18.000.000 đồng đối với hành vi điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 50 miligam đến 80 miligam/100 mililít máu.
6. Phạt tiền từ 30.000.000 đồng đến 40.000.000 đồng đối với hành vi điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu.

Điều 6. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ
1. Phạt tiền từ 100.000 đồng đến 200.000 đồng đối với hành vi không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường.
2. Phạt tiền từ 600.000 đồng đến 1.000.000 đồng đối với hành vi không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ).
3. Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với người điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn chưa vượt quá 50 miligam/100 mililít máu hoặc chưa vượt quá 0,25 miligam/1 lít khí thở.
4. Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu.
"""

# Mẫu 2: Nghị định 123/2021/NĐ-CP (Sửa đổi bổ sung Nghị định 100/2019/NĐ-CP)
DOC_123_2021 = """
CHÍNH PHỦ
Số: 123/2021/NĐ-CP
Hà Nội, ngày 28 tháng 12 năm 2021

NGHỊ ĐỊNH
Sửa đổi, bổ sung một số điều của các Nghị định quy định xử phạt vi phạm hành chính trong lĩnh vực hàng hải; giao thông đường bộ, đường sắt; hàng không dân dụng

Căn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015;
Căn cứ Luật Xử lý vi phạm hành chính ngày 20 tháng 6 năm 2012;
Căn cứ Nghị định số 100/2019/NĐ-CP;
Nghị định này có hiệu lực từ ngày 01 tháng 01 năm 2022.

CHƯƠNG I: SỬA ĐỔI NGHỊ ĐỊNH 100/2019/NĐ-CP

Điều 2. Sửa đổi, bổ sung Điều 5 Nghị định số 100/2019/NĐ-CP
1. Sửa đổi, bổ sung khoản 3 Điều 5 Nghị định số 100/2019/NĐ-CP như sau:
Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với người điều khiển xe ô tô thực hiện hành vi không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ hoặc đèn vàng).
2. Tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng đối với hành vi vi phạm tại khoản 1 Điều này.

Điều 3. Sửa đổi, bổ sung Điều 6 Nghị định số 100/2019/NĐ-CP
1. Sửa đổi, bổ sung điểm e khoản 4 Điều 6 Nghị định số 100/2019/NĐ-CP:
Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy không chấp hành hiệu lệnh của đèn tín hiệu giao thông.
"""

# Mẫu 3: Nghị định 168/2024/NĐ-CP (Quy định mới nhất xử phạt vi phạm giao thông đường bộ)
DOC_168_2024 = """
CHÍNH PHỦ
Số: 168/2024/NĐ-CP
Hà Nội, ngày 26 tháng 12 năm 2024

NGHỊ ĐỊNH
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ

Căn cứ Luật Trật tự, an toàn giao thông đường bộ số 36/2024/QH15;
Căn cứ Luật Xử lý vi phạm hành chính ngày 20 tháng 6 năm 2012;
Nghị định này có hiệu lực từ ngày 01 tháng 01 năm 2025.

CHƯƠNG I: QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Nghị định này quy định về hành vi vi phạm hành chính, hình thức xử phạt, mức xử phạt, biện pháp khắc phục hậu quả trong lĩnh vực giao thông đường bộ.
2. Nghị định này thay thế Nghị định số 100/2019/NĐ-CP và Nghị định số 123/2021/NĐ-CP kể từ ngày 01 tháng 01 năm 2025.

Điều 7. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông
1. Phạt tiền từ 500.000 đồng đến 800.000 đồng đối với hành vi không chấp hành hiệu lệnh của biển báo hiệu, vạch kẻ đường.
2. Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe ô tô không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ, vượt đèn vàng) và trừ 03 điểm giấy phép lái xe theo quy định tại Điều 12.
3. Phạt tiền từ 30.000.000 đồng đến 40.000.000 đồng và trừ 12 điểm giấy phép lái xe đối với hành vi điều khiển xe mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu.

Điều 8. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm
1. Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe mô tô không chấp hành hiệu lệnh của đèn tín hiệu giao thông và trừ 02 điểm giấy phép lái xe.
2. Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe mô tô có nồng độ cồn vượt quá 80 miligam/100 mililít máu.
"""

# Mẫu 4: Bộ luật Lao động số 45/2019/QH14
DOC_45_2019 = """
QUỐC HỘI
Số: 45/2019/QH14
Hà Nội, ngày 20 tháng 11 năm 2019

BỘ LUẬT LAO ĐỘNG

Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;
Quốc hội ban hành Bộ luật Lao động.
Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.

CHƯƠNG VII: THỜI GIỜ LÀM VIỆC, THỜI GIỜ NGHỈ NGƠI

Điều 105. Thời giờ làm việc bình thường
1. Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần.
2. Người sử dụng lao động có quyền quy định thời giờ làm việc theo ngày hoặc tuần nhưng phải thông báo cho người lao động biết; trường hợp theo tuần thì thời giờ làm việc bình thường không quá 10 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần.
3. Nhà nước khuyến khích người sử dụng lao động thực hiện tuần làm việc 40 giờ đối với người lao động.

Điều 107. Làm thêm giờ
1. Làm thêm giờ là khoảng thời gian làm việc ngoài thời giờ làm việc bình thường theo quy định của pháp luật, thỏa ước lao động tập thể hoặc nội quy lao động.
2. Người sử dụng lao động được sử dụng người lao động làm thêm giờ khi đáp ứng đầy đủ các yêu cầu sau đây:
a) Phải được sự đồng ý của người lao động theo quy định tại Điều 105;
b) Bảo đảm số giờ làm thêm của người lao động không quá 50% số giờ làm việc bình thường trong 01 ngày; trường hợp áp dụng quy định thời giờ làm việc bình thường theo tuần thì tổng số giờ làm việc bình thường và số giờ làm thêm không quá 12 giờ trong 01 ngày; không quá 40 giờ trong 01 tháng;
c) Bảo đảm số giờ làm thêm của người lao động không quá 200 giờ trong 01 năm, trừ trường hợp quy định tại khoản 3 Điều này.
"""

def seed_sample_laws(db: Session):
    """Nạp bộ dữ liệu pháp luật mẫu vào 3 kho."""
    samples = [
        {"text": DOC_100_2019, "sym": "100/2019/NĐ-CP", "domain": "giao_thong"},
        {"text": DOC_123_2021, "sym": "123/2021/NĐ-CP", "domain": "giao_thong"},
        {"text": DOC_168_2024, "sym": "168/2024/NĐ-CP", "domain": "giao_thong"},
        {"text": DOC_45_2019, "sym": "45/2019/QH14", "domain": "lao_dong"},
    ]
    
    results = []
    for item in samples:
        res = IngestionPipeline.ingest_document(
            db=db,
            raw_text=item["text"],
            doc_symbol_override=item["sym"],
            domain_override=item["domain"]
        )
        results.append(res)
    return results
