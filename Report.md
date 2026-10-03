# Báo Cáo Phân Tích Hệ Thống Memory Cho AI Agent (Day 17)

**Học viên:** Ngô Tiến Dũng  
**Mã học viên:** 2A202602374  
**Track:** Track 3, Phase 2 - Memory Systems for AI Agent  

---

## 1. Giới thiệu & Mục tiêu

Mục tiêu của bài nghiên cứu và thực nghiệm này là giải quyết một bài toán quan trọng trong việc đưa AI Agent vào môi trường thực tế: **Làm sao để Agent ghi nhớ thông tin người dùng lâu dài qua nhiều phiên làm việc (threads/sessions) độc lập mà vẫn kiểm soát được chi phí token và độ phình của ngữ cảnh.**

Trong bài lab này, chúng ta xây dựng và đánh giá hai kiến trúc Agent trên cùng một bộ dữ liệu tiếng Việt chuẩn:
1. **Baseline Agent (Agent A)**: Đại diện cho cách tiếp cận ngây thơ — chỉ lưu trữ bộ nhớ ngắn hạn trong phạm vi một thread (within-session memory) và không có cơ chế nén ngữ cảnh.
2. **Advanced Agent (Agent B)**: Đại diện cho kiến trúc bộ nhớ 3 tầng hoàn chỉnh:
   - **Tầng 1 (Short-term Memory)**: Cửa sổ trượt lưu giữ các lượt tương tác gần nhất (`keep_messages`).
   - **Tầng 2 (Persistent Memory - `User.md`)**: Lưu trữ các dữ kiện bền vững của người dùng trên đĩa (`state/profiles/<user_id>/User.md`) dưới dạng Markdown có cấu trúc.
   - **Tầng 3 (Compact Memory)**: Cơ chế nén tự động kích hoạt tóm tắt lịch sử cũ khi tổng lượng token trong phiên vượt ngưỡng an toàn (`compact_threshold_tokens`).

---

## 2. Kết quả Benchmark Thực Nghiệm

Hai Agent được đo lường độc lập trên 2 bộ benchmark tiêu chuẩn:
- **Bộ 1 (Standard Benchmark - `data/conversations.json`)**: Gồm 10 cuộc hội thoại (10 lượt/cuộc) với người dùng `dungct`, kiểm tra khả năng nhớ facts và xử lý đính chính thông tin qua các phiên.
- **Bộ 2 (Long-Context Stress Benchmark - `data/advanced_long_context.json`)**: Gồm 1 cuộc hội thoại dài 16 lượt dày đặc tin tức và dữ kiện phức tạp với người dùng `dungct_stress`, ép compact memory phải kích hoạt liên tục.

### 2.1. Bảng số liệu đo lường thực tế

#### Suite 1: Standard Benchmark (10 conversations)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 2,847 | 20,870 | **0.0%** | 15.0% | 0 | 0 |
| **Advanced** | 2,993 | 35,028 | **100.0%** | **89.0%** | 539 B | 0 |

#### Suite 2: Long-Context Stress Benchmark (16 long turns)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 496 | 26,683 | **0.0%** | 15.0% | 0 | 0 |
| **Advanced** | 832 | **14,270** | **100.0%** | **100.0%** | 406 B | **4** |

---

## 3. Phân tích Chuyên Sâu Các Trade-Off

### 3.1. Vì sao Advanced Agent có Recall vượt trội (100% vs 0%)?
- **Baseline Agent**: Dữ liệu chỉ tồn tại trong bộ nhớ RAM của một `thread_id`. Khi hệ thống đặt câu hỏi kiểm tra trí nhớ (`recall_questions`) tại một thread mới (đại diện cho một phiên làm việc mới hôm sau hoặc người dùng mở tab mới), Baseline hoàn toàn không có dữ liệu ➔ **Recall đạt 0.0%**.
- **Advanced Agent**: Mỗi khi người dùng chia sẻ dữ kiện (tên, nơi ở, đồ uống, sở thích), Agent trích xuất và đồng bộ ngay lập tức vào file `User.md`. Khi bắt đầu thread mới, Agent chủ động nạp `User.md` vào ngữ cảnh prompt hoặc công cụ đọc profile ➔ **Recall đạt 100.0%**, trả lời chính xác mọi câu hỏi từ đơn giản đến phức tạp.

### 3.2. Vì sao ở hội thoại ngắn, Advanced Agent tốn Prompt Tokens hơn Baseline (35,028 vs 20,870)?
- Ở các cuộc hội thoại ngắn (10 lượt ngắn, chưa chạm ngưỡng `compact_threshold_tokens = 1200`), Compact Memory chưa kích hoạt (`Compactions = 0`).
- Trong mỗi lượt gọi mô hình, Advanced Agent phải "gánh" thêm phần dữ liệu của `User.md` (hồ sơ người dùng) được nạp vào System Prompt. 
- **Kết luận**: Đây là chi phí đánh đổi tất yếu (trade-off) của bộ nhớ dài hạn: muốn Agent nhớ xuyên suốt phiên làm việc, ta phải chấp nhận một lượng "overhead prompt tokens" cố định ở các hội thoại ngắn.

### 3.3. Vì sao Compact Memory giúp Advanced Agent chiến thắng áp đảo ở hội thoại dài (14,270 vs 26,683 tokens)?
- Trong bài test stress 16 lượt dài:
  - **Baseline Agent** không có cơ chế nén: Đến lượt thứ 16, nó phải kéo theo toàn bộ văn bản của 15 lượt trước đó. Lượng prompt context phình to theo cấp số cộng: $\sum_{i=1}^{N} \text{turn}_i$, dẫn đến tổng token prompt tích lũy lên tới **26,683 tokens**.
  - **Advanced Agent** áp dụng `CompactMemoryManager`: Khi tổng token vượt quá 1200, hệ thống đã kích hoạt **4 lần nén (compactions)**, tóm tắt các lượt trao đổi cũ và chỉ giữ lại 4 tin nhắn gần nhất (`compact_keep_messages = 4`). 
- **Kết quả**: Prompt context của Advanced luôn được "neo" ở mức an toàn (~500 - 1200 tokens), giúp **tiết kiệm gần 50% chi phí xử lý prompt**, đồng thời giảm thiểu đáng kể độ trễ (latency) của mô hình.

### 3.4. Tốc độ tăng trưởng của Memory File (`User.md`) và Rủi ro đi kèm
- **Tốc độ phình to**: Trong 10 cuộc hội thoại, file `User.md` phình thêm **539 bytes** (khoảng ~150 tokens). Đây là mức tăng trưởng rất khiêm tốn và an toàn.
- **Rủi ro kỹ thuật**:
  1. *Lưu trữ rác / Fact không quan trọng*: Nếu người dùng nói chuyện phiếm mà cái gì Agent cũng ghi vào `User.md`, file sẽ phình lên hàng megabytes, làm tràn context window khi inject vào System Prompt.
  2. *Lưu sai thông tin (Hallucination)*: Người dùng nói đùa hoặc đưa ra giả định tạm thời mà Agent ghi thành sự thật vĩnh viễn.

---

## 4. Các Tính Năng Bonus Đã Triển Khai (Mức 90 - 100 Điểm)

Để giải quyết triệt để các rủi ro trên, hệ thống đã triển khai 4 cơ chế nâng cao:

### 4.1. Conflict & Correction Handling (Xử lý xung đột và đính chính)
- **Vấn đề**: Người dùng thay đổi thông tin theo thời gian (ví dụ: ban đầu ở Đà Nẵng, sau đó chuyển sang Huế; ban đầu làm Backend, sau đó chuyển sang MLOps).
- **Giải pháp**: Cơ chế `extract_profile_updates` kết hợp với `UserProfileStore.update_facts` nhận diện các từ khóa đính chính (`chứ không còn ở`, `chuyển sang`, `đính chính`, `thực ra`) để ghi đè fact mới nhất, loại bỏ hoàn toàn fact cũ.
- **Hiệu quả**: Trong câu hỏi kiểm tra ở Conv 6 và Stress test, Agent trả lời chính xác nơi ở hiện tại là Đà Nẵng/Huế và nghề nghiệp là MLOps, không bị lẫn lộn giữa nghề cũ và nghề mới.

### 4.2. Noise Filtering (Lọc nhiễu và câu đùa)
- **Vấn đề**: Trong Stress Test turn 10, người dùng đùa: *"đùa với đồng nghiệp là chuyển sang product manager"* và *"Hà Nội chỉ là nơi vừa bay ra họp 2 ngày"*.
- **Giải pháp**: Bộ lọc phát hiện ngữ cảnh đùa (`chỉ là câu đùa`) và ngữ cảnh tạm thời (`bay ra họp`) để **tuyệt đối không ghi** `product manager` hay `Hà Nội` vào `User.md`.

### 4.3. Question Filtering & Tiếng Việt Đa Nghĩa
- **Vấn đề**:
  - Khi người dùng hỏi: *"Bạn có biết DũngCT không?"* hoặc *"Mình là ai?"*, nhiều Agent ngây thơ trích xuất chữ "ai" thành mối quan tâm "AI" (Artificial Intelligence).
  - Khi người dùng chỉ hỏi kiểm tra trí nhớ, Agent không được ghi đè câu hỏi thành fact.
- **Giải pháp**: 
  - Regex phân biệt ngữ nghĩa: Phân biệt từ đại từ tiếng Việt ("ai đó", "mình là ai") với chữ viết tắt `AI` (Trí tuệ nhân tạo), `AI agent`, `startup AI`.
  - Bỏ qua các lượt thuần túy là câu hỏi kiểm tra (`is_pure_question`).

### 4.4. Structured Entity Extraction & Interests Merging
- Thay vì ghi text tự do, facts được lưu có cấu trúc: `name`, `location`, `profession`, `favorite_drink`, `favorite_food`, `pet`, `response_style`, `interests`.
- Riêng đối với mối quan tâm kỹ thuật (`interests`), hệ thống tự động gộp (merge) danh sách không trùng lặp (`Python, AI, MLOps`) thay vì ghi đè làm mất sở thích cũ.

---

## 5. Kết Luận

Kiến trúc bộ nhớ 3 tầng (Short-term + Persistent Markdown + Compact Memory) chứng minh tính hiệu quả vượt trội trong thực tế:
- Đảm bảo tính nhất quán và trí nhớ dài hạn (Recall 100%).
- Tiết kiệm 50% chi phí xử lý ngữ cảnh trên các chuỗi hội thoại dài.
- Cân bằng hoàn hảo giữa hiệu năng, chi phí token và độ tin cậy của AI Agent.
