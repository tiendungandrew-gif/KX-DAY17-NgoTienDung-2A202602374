# Báo Cáo Phân Tích Kết Quả (Bước 8 - GUIDE.md)

**Học viên:** Ngô Tiến Dũng  
**MSSV:** 2A202602374  
**Repo:** KX-DAY17-NgoTienDung-2A202602374  

---

## 1. Kết Quả Đo Lường Thực Tế

### 1.1. Standard Benchmark (`data/conversations.json` - 10 hội thoại)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 2,847 | 20,870 | **0.0%** | 15.0% | 0 | 0 |
| **Advanced** | 2,993 | 35,028 | **100.0%** | **89.0%** | 539 B | 0 |

### 1.2. Long-Context Stress Benchmark (`data/advanced_long_context.json` - 16 lượt dài)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 496 | 26,683 | **0.0%** | 15.0% | 0 | 0 |
| **Advanced** | 832 | **14,270** | **100.0%** | **100.0%** | 406 B | **4** |

---

## 2. Trả Lời 4 Câu Hỏi Trọng Tâm Của Bước 8 (GUIDE.md)

### Câu hỏi 1: Vì sao Advanced Agent có Recall tốt hơn Baseline Agent?
- **Baseline Agent** chỉ có *within-session memory* (bộ nhớ tạm lưu theo `thread_id`). Khi chuyển sang một thread mới (đại diện cho một phiên làm việc mới độc lập), Baseline hoàn toàn không có lịch sử hội thoại trước đó, dẫn đến việc không thể trả lời bất kỳ thông tin nào về người dùng (**Recall đạt 0.0%**).
- **Advanced Agent** được trang bị tầng *Persistent Memory (`User.md`)* trên đĩa. Mọi thông tin ổn định (tên, nơi ở, nghề nghiệp, sở thích) được trích xuất và đồng bộ ngay vào file hồ sơ người dùng. Khi bước vào thread mới, Agent đọc trực tiếp từ `User.md` để trả lời chính xác các câu hỏi kiểm tra trí nhớ (**Recall đạt 100.0%**).

### Câu hỏi 2: Vì sao Advanced Agent có thể tốn hơn ở hội thoại ngắn?
- Ở các cuộc hội thoại ngắn (như 10 cuộc hội thoại trong Standard Benchmark), số lượng token trong thread chưa vượt ngưỡng kích hoạt nén (`compact_threshold_tokens = 1200`), do đó không có lần nén nào diễn ra (`Compactions = 0`).
- Tuy nhiên, trong mỗi lượt phản hồi, Advanced Agent phải nạp thêm toàn bộ nội dung của file `User.md` vào ngữ cảnh prompt để duy trì persona và hiểu người dùng. Lượng dữ liệu bổ sung này tạo ra một khoản chi phí cố định (overhead tokens) cho mỗi lượt chat, khiến tổng `Prompt tokens processed` của Advanced cao hơn Baseline (35,028 so với 20,870 tokens).
- **Ý nghĩa trade-off**: Ở các tương tác ngắn hạn, chi phí token của hệ thống có persistent memory sẽ cao hơn agent ngây thơ để đánh đổi lấy khả năng thấu hiểu người dùng lâu dài.

### Câu hỏi 3: Vì sao Compact Memory giúp Advanced Agent có lợi thế ở hội thoại dài?
- Trong chuỗi hội thoại dài (như Stress Test 16 lượt dày đặc thông tin):
  - **Baseline Agent** giữ nguyên toàn bộ lịch sử hội thoại thô. Càng về các lượt sau, ngữ cảnh gửi kèm càng phình to theo cấp số cộng, dẫn đến tổng lượng prompt tích lũy lên tới **26,683 tokens**.
  - **Advanced Agent** kích hoạt cơ chế `CompactMemoryManager`: Khi tổng token vượt ngưỡng 1200, hệ thống tự động nén các tin nhắn cũ thành bản tóm tắt súc tích (`summary`) và chỉ giữ lại 4 tin nhắn gần nhất (`compact_keep_messages = 4`). Quá trình này đã kích hoạt **4 lần nén**.
- **Kết quả**: Ngữ cảnh prompt của Advanced luôn được kiểm soát trong khoảng an toàn, giảm tổng `Prompt tokens processed` xuống chỉ còn **14,270 tokens** (**tiết kiệm gần 50% chi phí token**) so với Baseline, đồng thời giảm độ trễ và tránh nguy cơ tràn context window của LLM.

### Câu hỏi 4: File memory tăng trưởng ra sao và rủi ro gì đi kèm?
- **Tốc độ tăng trưởng**: Trong 10 cuộc hội thoại mẫu, file `User.md` chỉ tăng **539 bytes** (khoảng ~150 tokens) nhờ cơ chế trích xuất có chọn lọc các fact ổn định thay vì lưu toàn văn cuộc trò chuyện.
- **Rủi ro đi kèm**:
  1. *Rủi ro phình rác ngữ cảnh (Memory Bloat)*: Nếu không có bộ lọc tốt, những thông tin rác, câu chuyện phiếm sẽ bị ghi vào `User.md`, làm file phình to và lãng phí token mỗi khi inject vào prompt.
  2. *Rủi ro lưu sai / Lưu thông tin cũ (Conflict & Hallucination)*: Người dùng có thể nói đùa (như đùa làm "product manager") hoặc thay đổi thông tin (đổi nơi ở từ Đà Nẵng sang Huế). Nếu không có cơ chế phát hiện xung đột và đính chính (correction handling), Agent sẽ lưu trữ thông tin mâu thuẫn hoặc sai lệch.
- **Giải pháp đã triển khai trong bài làm**: Hệ thống đã bổ sung bộ lọc nhiễu (loại bỏ câu đùa, địa điểm công tác tạm thời), lọc câu hỏi (không ghi đè câu hỏi thành fact), và cơ chế cập nhật ghi đè fact mới nhất khi người dùng đính chính.
