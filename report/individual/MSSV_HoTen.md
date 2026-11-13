# Báo cáo cá nhân — Day 6

> Đổi tên file thành `<MSSV>_<HoTen>.md`. Các nhãn thủ công (coherence, metadata, grounding) bên dưới là **nháp do trợ lý AI tạo bằng quy tắc**; tác giả cần đọc, điền `author_label` trong `starter/results/audit_*.csv` và cập nhật mục này trước khi nộp.

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang:** quản trị rủi ro AI của NIST. `nist-ai-100-1` (AI RMF 1.0, 01/2023; 48 trang vật lý, tính 40) và `nist-ai-600-1` (GAI Profile, 07/2024; 64 trang, tính 52): **92 trang**. Ấn phẩm của cơ quan liên bang Mỹ, không có bản quyền ở Mỹ; tải ngày 2026-11-13 từ nvlpubs.nist.gov. Quy tắc tính: chỉ các trang thân bài (AI 100-1: 6–47; AI 600-1: 5–57), loại bìa, thông báo, mục lục, tài liệu tham khảo, trang cuối, và trang <500 ký tự sau khi bỏ header/footer (AI 100-1 tr.16, 39; AI 600-1 tr.50). Chi tiết, sha256 và danh sách trang: `data/manifest.json`.
- **Chuẩn hóa, lỗi, giới hạn:** `pdftotext` (poppler), PDF gốc có text nên không cần OCR; chuẩn hóa ligature, bỏ header/footer lặp, gộp khoảng trắng. Mất: hình (Fig. 1–3 AI RMF), xuống dòng/đoạn (nên không chunk theo đoạn được), bảng nhiều cột của AI 600-1 bị trải phẳng, chân trang "Page N" còn lẫn trong text của AI 100-1.
- **Embedding/vector store:** `BAAI/bge-small-en-v1.5` qua fastembed 0.9.1 (ONNX, local), 384 chiều, vector chuẩn hóa; query thêm prefix hướng dẫn của bge. PostgreSQL 16.16 + pgvector 0.8.7, cosine, tìm kiếm chính xác (không index ANN), bảng `chunks`, volume Docker bền vững. Lệnh chạy ở [README.md](../../README.md). Chi phí 0 USD (không dùng API trả phí).
- **Metadata:** bắt buộc `document_id`, `source`, `page` (trang vật lý) + `printed_page`. Trường lọc: `document_id`, `function` (GOVERN/MAP/MEASURE/MANAGE), `section`, `year`. Nguồn giá trị: `document_id`/`year` từ tài liệu; `section` theo mục lục từng tài liệu; `function` của AI 100-1 từ tiêu đề trang, của AI 600-1 suy ra từ mã action chiếm nhiều nhất trên trang (xấp xỉ ở trang giáp ranh).

## Cấu hình và benchmark
- **A:** cố định 500 ký tự, overlap 50 (555 chunk). **B:** gom nguyên câu tới tối đa 1000 ký tự, không overlap (304 chunk; không chunk theo đoạn vì mất xuống dòng khi trích). **C:** giống B (cùng chunk và vector), chỉ thêm filter metadata ở query khi câu hỏi có filter. A–B chỉ đổi chunking; B–C chỉ đổi filter.
- **Benchmark:** 20 câu, 15 dev (q01–q15) / 5 test (q16–q20), chia trước khi chạy. 3 câu filter: q07, q14 (dev), q17 (test). Mỗi `evidence_quote` được `benchmark/verify_gold.py` kiểm chứng nguyên văn trên trang gold. Xem `benchmark/README.md`.
- **Tiêu chí chọn (chốt trước khi xem test):** ưu tiên dev Hit@3, sau đó coherence, rồi tài nguyên.

## Kết quả
| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian ingest | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 10/15 | 11/15 | 555 | 8.7 s | 0 |
| A | test | 2/5 | 4/5 | 555 | | 0 |
| B | dev | 11/15 | 13/15 | 304 | 8.7 s | 0 |
| B | test | 2/5 | 3/5 | 304 | | 0 |
| C | dev | 11/15 | 14/15 | 304 | 0.1 s (dùng lại vector B) | 0 |
| C | test | 2/5 | 3/5 | 304 | | 0 |

Thời gian ingest gồm embed và ghi DB; mỗi strategy một lần chạy, đo trên máy cá nhân (macOS, CPU). Toàn bộ lệnh `src.run` ~19 s sau khi model đã tải.

| Strategy | Coherence TB /2 (n=10) | Metadata đủ và đúng (n/N) | Filter tuân thủ | Grounding 0/1/2 (số câu), TB /2 |
|---|---|---|---|---|
| A | 0.0 (nháp) | 15/15 (tự động) | N/A (không filter) | 1/0/4, 1.6 (nháp) |
| B | 2.0 (nháp) | 15/15 (tự động) | N/A (không filter) | 1/1/3, 1.4 (nháp) |
| C | 2.0 (nháp) | 15/15 (tự động) | 1/1 | 1/1/3, 1.4 (nháp) |

Trace: `starter/results/traces.jsonl` (top-3 đầy đủ, score, metadata); số liệu: `summary.json`; log chạy: `run.log`; phiên bản: `env.txt`. Mẫu coherence: 10 page ID đầu theo thứ tự (`nist-ai-100-1#p006…p015`), vị trí ở 40% độ dài trang, chốt trước khi chấm. Metadata/grounding: toàn bộ 5 câu test × top-3. Metadata kiểm tự động so với `pages.jsonl`, chưa so thủ công với PDF.

## Phân tích và kết luận
- **A–B:** dev Hit@3 +2 (11→13) vì A cắt evidence giữa hai chunk ở q04 và q12 (đúng trang nhưng không đủ quote); test Hit@3 −1 do q19. **B–C:** dev Hit@3 +1 (q14), Hit@1 và test không đổi.
- **Ví dụ sai:** *q06* (`nist-ai-100-1` tr.27, "cross-cutting function"): cả ba cấu hình trượt, top-3 của B là đoạn giới thiệu Core (tr.25, 8, 47), nên câu diễn đạt lại không khớp ngữ nghĩa. *q18* (`nist-ai-600-1` tr.36, MS-2.6-007): cả ba trượt, top-3 của B là các đoạn ở tr.49, 16, 24 (ứng phó sự cố, giới thiệu, chia sẻ thông tin); quote cũng bị cắt ở chỗ ngắt cột của bảng.
- **Chiến lược chọn:** C, theo tiêu chí đã chốt (dev Hit@3 cao nhất 14/15, coherence nháp tốt). Điều kiện áp dụng: người dùng biết trước `document_id`/`function`; ở các câu không filter, C = B. Đánh đổi: B có chunk dài (median 849 ký tự) và chunk ngắn bất thường (nhỏ nhất 7 ký tự); A chính xác hơn về vị trí nhưng cắt bằng chứng.
- **Hạn chế:** 20 câu, một người viết câu hỏi và nhãn; test 5 câu nên chênh 1 câu (q19) là toàn bộ khác biệt A–B ở test; chỉ một embedding model; không rerank; nhãn coherence/grounding mới là nháp; q19 có đoạn định nghĩa tương đương ở tr.54 chưa được xác nhận nên không tính; thời gian đo một lần; giá trị filter hiệu quả chỉ được chứng minh ở q14.
- **Mở rộng:** chunk theo cấu trúc (tách bảng action theo từng Action ID), reranker hoặc hybrid BM25, thêm câu test và nhãn từ người thứ hai, thử model khác với cùng benchmark.
