import os
import sys
import json
import time
import subprocess
from multiprocessing import Process, Manager
from openai import OpenAI

# Khởi tạo API (Đọc từ GitHub Secrets)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def generate_ai_code(prompt):
    """Gọi LLM sinh code. Bước này KHÔNG tính giờ đua."""
    print("  -> Đang gọi AI (GPT-4) sinh code...")
    system_msg = "Bạn là lập trình viên giỏi. Chỉ trả về duy nhất code Python, không bọc trong markdown ```python, không giải thích."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo", # Có thể đổi thành gpt-3.5-turbo cho rẻ
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ]
        )
        code = response.choices[0].message.content.strip()
        if code.startswith("```python"):
            code = code.split("```python")[1].split("```")[0].strip()
        elif code.startswith("```"):
            code = code.split("```")[1].split("```")[0].strip()
        return code
    except Exception as e:
        print(f"Lỗi khi gọi API: {e}")
        return ""

def run_script(script_path, input_data, result_dict, key_time, key_output):
    """Chạy một file python với input JSON và ghi lại thời gian."""
    start_time = time.perf_counter()
    try:
        process = subprocess.run(
            ['python', script_path],
            input=json.dumps(input_data),
            text=True,
            capture_output=True,
            check=True,
            timeout=10 # Giới hạn 10 giây để không bị treo
        )
        end_time = time.perf_counter()
        result_dict[key_time] = end_time - start_time
        result_dict[key_output] = json.loads(process.stdout)
    except Exception as e:
        result_dict[key_time] = float('inf')
        result_dict[key_output] = None
        print(f"\n  [Lỗi chạy code {script_path}]: {e}")

def main():
    tasks_dir = "tasks"
    private_dir = "private_repo" # Nơi Github Actions sẽ clone private repo vào
    
    total_points = 0
    num_tasks = 0

    os.makedirs("temp", exist_ok=True)

    # Quét tất cả các bài toán trong thư mục tasks
    for task_file in sorted(os.listdir(tasks_dir)):
        if not task_file.endswith(".json"): continue
        num_tasks += 1
        task_id = task_file.split("_")[0]
        print(f"\n{'='*40}\nĐang xử lý Task {task_id}\n{'='*40}")
        
        # Đọc đề bài
        with open(os.path.join(tasks_dir, task_file), 'r') as f:
            task_data = json.load(f)
        
        # Đường dẫn file bí mật (sẽ được tải về sau)
        opt_path = os.path.join(private_dir, "optimized", f"{task_id}_opt.py")
        ans_path = os.path.join(private_dir, "answers", f"{task_id}_ans.json")
        ai_path = os.path.join("temp", f"{task_id}_ai.py")

        # 1. AI sinh code (KHÔNG TÍNH GIỜ ĐUA)
        ai_code = generate_ai_code(task_data["prompt"])
        with open(ai_path, 'w', encoding='utf-8') as f:
            f.write(ai_code)

        # Kiểm tra xem có file bí mật không (đề phòng lỗi Github Actions)
        if not os.path.exists(opt_path) or not os.path.exists(ans_path):
            print(f"LỖI: Không tìm thấy file bí mật cho Task {task_id}. Bạn đã cấu hình Token đúng chưa?")
            continue

        # 2. Chuẩn bị biến chia sẻ giữa các Process
        with Manager() as manager:
            shared_results = manager.dict()
            
            p_ai = Process(target=run_script, args=(ai_path, task_data["input_data"], shared_results, 't_ai', 'out_ai'))
            p_opt = Process(target=run_script, args=(opt_path, task_data["input_data"], shared_results, 't_opt', 'out_opt'))

            print("  -> Bắt đầu cuộc đua thời gian!")
            
            # 3. Kích hoạt chạy CÙNG LÚC
            p_ai.start()
            p_opt.start()

            p_ai.join()
            p_opt.join()

            t_ai = shared_results.get('t_ai', float('inf'))
            t_opt = shared_results.get('t_opt', float('inf'))
            out_ai = shared_results.get('out_ai')
            
            # Đọc đáp án chuẩn
            with open(ans_path, 'r') as f:
                correct_ans = json.load(f)

            # 4. Chấm điểm
            is_correct = (out_ai == correct_ans)
            point = 0.0
            
            if is_correct:
                if t_ai < t_opt: point = 1.0
                elif t_ai <= 2.0 * t_opt: point = 0.25
                else: point = 0.1
                    
            total_points += point
            
            print(f"\n  KẾT QUẢ TASK {task_id}:")
            print(f"  - AI trả lời: {out_ai} -> {'[ĐÚNG]' if is_correct else '[SAI]'} (Đáp án chuẩn: {correct_ans})")
            if is_correct:
                print(f"  - Thời gian AI   : {t_ai:.5f} giây")
                print(f"  - Thời gian Opt  : {t_opt:.5f} giây")
                print(f"  => Điểm nhận được: +{point} điểm")

    # Tổng kết
    print(f"\n{'*'*40}\nKẾT QUẢ CHUNG CUỘC\n{'*'*40}")
    print(f"Tổng điểm: {total_points}/{num_tasks}")
    accuracy = (total_points / num_tasks) * 100 if num_tasks > 0 else 0
    print(f"Tỉ lệ thành tích: {accuracy:.2f}%")

if __name__ == "__main__":
    main()
