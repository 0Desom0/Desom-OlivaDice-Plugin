import openpyxl
from pathlib import Path
import sys
from typing import List, Tuple, Dict, Any

# 添加上级目录到系统路径，以便导入文档2的函数
sys.path.append(str(Path(__file__).parent.parent))
from function import load_song_data, find_song_by_search_term  # 假设文档2的文件名为"文档2.py"

def process_excel(input_path: str, output_path: str) -> None:
    """
    处理Excel文件，将B列的歌曲名搜索后写入A列的章节号
    
    Args:
        input_path: 输入Excel文件路径
        output_path: 输出Excel文件路径
    """
    # 加载歌曲数据
    song_data = load_song_data()
    if not song_data:
        print("无法加载歌曲数据，请检查歌曲数据文件")
        return
    
    # 打开Excel文件
    try:
        wb = openpyxl.load_workbook(input_path)
        sheet = wb['Sheet1']
    except Exception as e:
        print(f"打开Excel文件失败: {str(e)}")
        return
    
    # 处理每一行
    for row in sheet.iter_rows(min_row=1, max_col=2):
        song_name = row[1].value  # B列
        if not song_name:
            continue
            
        # 搜索歌曲
        matched_songs, _, total_count = find_song_by_search_term(str(song_name), song_data)
        
        # 只有当找到唯一结果时才写入章节号
        if total_count == 1:
            chapter = matched_songs[0]['chapter']
            row[0].value = chapter  # 写入A列
        else:
            row[0].value = None  # 确保没有匹配时清空单元格
    
    # 保存为新的Excel文件
    try:
        wb.save(output_path)
        print(f"处理完成，结果已保存到 {output_path}")
    except Exception as e:
        print(f"保存Excel文件失败: {str(e)}")

if __name__ == "__main__":
    # 用户输入路径
    input_excel = input("请输入输入Excel文件路径: ")
    output_excel = input("请输入输出Excel文件路径: ")
    
    # 验证路径
    if not Path(input_excel).exists():
        print(f"输入文件不存在: {input_excel}")
        sys.exit(1)
    
    # 处理文件
    process_excel(input_excel, output_excel)