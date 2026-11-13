# Phân tích GUIDE §4 (năm khía cạnh)

Corpus: NIST AI 100-1 + AI 600-1, 92 trang nội dung. Benchmark 20 câu (15 dev / 5 test). Embedding `BAAI/bge-small-en-v1.5` (fastembed 0.9.1, 384 chiều, local, chi phí 0), PostgreSQL 16 + pgvector 0.8.7, cosine, tìm kiếm chính xác (không ANN). Query dùng prefix hướng dẫn của bge. Chạy: `cd starter && python -m src.run && python -m src.audit` (venv Python 3.12; Python 3.15 chưa có wheel onnxruntime). Dữ liệu thô: `results/traces.jsonl`, `summary.json`.

## 1. Retrieval accuracy (tự động, n/N)

| Chiến lược | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---|---|---|---|
| A fixed 500/50 | 10/15 | 11/15 | 2/5 | 4/5 |
| B câu, ≤1000 | 11/15 | 13/15 | 2/5 | 3/5 |
| C = B + filter | 11/15 | 14/15 | 2/5 | 3/5 |

Hit = đúng `document_id` + trang gold **và** chứa trọn `evidence_quote`. Lỗi: q06 trượt ở cả 3 cấu hình (câu hỏi diễn đạt lại "cross-cutting", top-3 là các đoạn giới thiệu Core); q18 trượt ở cả 3 (bảng action bị nối lẫn cột, top-3 là các action về giám sát/ứng phó sự cố, không phải MS-2.6-007); q19 trúng ở A nhưng không ở B/C (top-3 của B/C là các đoạn red-teaming ở trang 54–55, định nghĩa gold ở trang 53 không lọt top-3). Với A, q04 và q12 đúng trang nhưng evidence bị cắt giữa hai chunk (`page_only_misses` = 2 dev). Tập test 5 câu quá nhỏ: chênh 1 câu (q19) là toàn bộ khác biệt A–B ở test.

Ghi chú: q19 có đoạn định nghĩa tương đương ở trang 54 (top-1 của A); chưa được tác giả xác nhận nên không tính vào chỉ số chính.

## 2. Chunk coherence (nhãn nháp)

Mẫu cố định trước khi chấm: 10 page ID đầu theo thứ tự (`nist-ai-100-1#p006…p015`), vị trí = ký tự ở 40% độ dài trang. Nhãn nháp theo quy tắc (2 = bắt đầu và kết thúc ở ranh giới câu; 1 = cắt ở rìa nhưng không giữa từ; 0 = cắt giữa từ): A = 0/10 điểm 2 (trung bình 0.0/2, cả 10 chunk bị cắt giữa từ); B/C = 10/10 điểm 2 (2.0/2). Quy tắc thô: B chưa chứng minh là "giữ trọn ý" ngoài ranh giới câu; chunk B có thể chứa nhiều ý hoặc kết thúc bằng chân trang "Page N". Cần tác giả đọc và điền `author_label` trong `audit_coherence.csv`.

## 3. Metadata usefulness

Kiểm tra tự động 5 câu test × top-3 = 15 bản ghi mỗi chiến lược: text chunk nằm trong trang nguồn, `source`, `printed_page`, `section`, `function`, `year`, và tuân thủ filter đều khớp `pages.jsonl`: **15/15** cho A, B, C; filter tuân thủ **1/1** (q17, C). Đây chỉ kiểm tra khớp với bản trích xuất, chưa phải đối chiếu thủ công với PDF gốc. Trường hữu ích: `document_id`/`function` lọc theo tài liệu hoặc chức năng GOVERN/MAP/MEASURE/MANAGE; ở q14 filter đưa gold từ không có trong top-3 (B) lên rank 2 (C). Hạn chế: `function` của AI 600-1 suy ra từ mã action nhiều nhất trên trang nên sai ở trang giáp ranh; q07 và q17 chạy đúng ngay cả khi không filter, nên giá trị của filter chỉ chứng minh trên 1 câu (q14).

## 4. Grounding quality (nhãn nháp, 5 câu test, 0/1/2)

A: 2×4, 0×1 (trung bình 1.6/2). B và C: 2×3, 1×1 (q19: top-3 là đoạn red-teaming nhưng không có định nghĩa), 0×1 (q18) (trung bình 1.4/2). Chỉ đánh giá bằng chứng truy xuất, không phải độ đúng câu trả lời LLM. Nhãn là nháp của trợ lý AI, cần tác giả xác nhận trong `audit_grounding.csv`.

## 5. Tác động chiến lược

- A→B (chỉ đổi chunking): dev Hit@3 +2 (11→13) nhờ không cắt evidence (q04, q12); test Hit@3 −1 (q19). Coherence tăng từ 0.0 lên 2.0 (nháp). Tốn tài nguyên: A 555 chunk, B 304 chunk; thời gian ingest tương đương (~9s mỗi lần), chi phí 0.
- B→C (chỉ thêm filter): dev Hit@3 +1 (q14), Hit@1 không đổi, test không đổi. Chunk và vector dùng chung với B nên chi phí thêm bằng 0.
- Đánh đổi: B giữ trọn câu nhưng chunk dài (median 849 ký tự), có thể làm loãng vector khi câu hỏi nhắm một câu đơn (giả thuyết cho q19, chưa kiểm chứng). A chính xác về vị trí nhưng cắt bằng chứng.
- Tiêu chí chọn (định nghĩa trước khi đọc test): ưu tiên dev Hit@3, rồi coherence, rồi tài nguyên → chọn **C**. Test (3/5 so với 4/5 của A) không đủ mẫu để đảo quyết định.
- Giới hạn: n=20, một người viết câu hỏi và nhãn, chỉ một embedding model, không rerank, `function` có thể sai ở trang giáp ranh, chân trang "Page N" lẫn trong text, bảng nhiều cột bị trải phẳng. Không suy rộng ngoài corpus này.
