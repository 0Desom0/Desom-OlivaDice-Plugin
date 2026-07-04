import json
from pathlib import Path

def check_missing_songs(json_file, expected_count=None):
    """检查缺失的乐曲ID"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            songs = json.load(f)
    except FileNotFoundError:
        print(f"错误：找不到文件 {json_file}")
        return
    except json.JSONDecodeError:
        print(f"错误：文件 {json_file} 不是有效的JSON格式")
        return

    if not songs:
        print("警告：乐曲列表为空")
        return

    # 如果没有提供expected_count，则自动检测最大ID
    if expected_count is None:
        expected_count = max(song['id'] for song in songs)
        print(f"自动检测到最大ID: {expected_count}")

    # 获取所有存在的ID
    existing_ids = {song['id'] for song in songs}
    
    # 检查缺失的ID
    missing_ids = []
    for id in range(1, expected_count + 1):
        if id not in existing_ids:
            missing_ids.append(id)
    
    # 检查重复的ID
    id_counts = {}
    for song in songs:
        id = song['id']
        id_counts[id] = id_counts.get(id, 0) + 1
    
    duplicate_ids = [id for id, count in id_counts.items() if count > 1]
    
    # 检查必填字段是否为空
    invalid_songs = []
    required_fields = ['title', 'artist', 'chapter', 'category']
    for song in songs:
        for field in required_fields:
            if not song.get(field):
                invalid_songs.append((song['id'], field))
                break
    
    # 打印结果
    print(f"\n检查结果:")
    print(f"已加载乐曲数量: {len(songs)}")
    print(f"预期乐曲数量: {expected_count}")
    
    if missing_ids:
        print(f"\n缺失的ID ({len(missing_ids)}个):")
        # 分组显示缺失ID
        groups = []
        if missing_ids:
            start = missing_ids[0]
            prev = start
            for id in missing_ids[1:]:
                if id != prev + 1:
                    groups.append((start, prev))
                    start = id
                prev = id
            groups.append((start, prev))
        
        for start, end in groups:
            if start == end:
                print(f"  {start}")
            else:
                print(f"  {start}-{end}")
    else:
        print("\n没有缺失的ID")
    
    if duplicate_ids:
        print(f"\n重复的ID ({len(duplicate_ids)}个):")
        for id in duplicate_ids:
            print(f"  ID {id} 出现了 {id_counts[id]} 次")
    else:
        print("\n没有重复的ID")
    
    if invalid_songs:
        print(f"\n必填字段缺失的乐曲 ({len(invalid_songs)}个):")
        for id, field in invalid_songs:
            print(f"  ID {id}: 缺少字段 '{field}'")
    else:
        print("\n所有乐曲的必填字段完整")

    # 检查时间字段为空的情况
    empty_time = [song['id'] for song in songs if not song.get('time')]
    if empty_time:
        print(f"\n时间字段为空的乐曲 ({len(empty_time)}个):")
        print("  " + ", ".join(map(str, empty_time)))

def get_user_input():
    """获取用户输入的JSON文件路径"""
    while True:
        file_path = input("请输入song_list.json的完整路径(或拖放文件到此处): ").strip('"\' ')
        if not file_path:
            print("路径不能为空，请重新输入")
            continue
        
        path = Path(file_path)
        if not path.exists():
            print(f"文件不存在: {file_path}")
            continue
            
        if path.suffix.lower() != '.json':
            print("请指定一个.json文件")
            continue
            
        return path

if __name__ == "__main__":
    print("=== Lanota乐曲数据检查工具 ===")
    print("本工具用于检查song_list.json中的缺失ID和字段完整性\n")
    
    json_file = get_user_input()
    
    # 询问用户是否要指定最大ID
    max_id_input = input("请输入预期的最大ID(留空则自动检测): ").strip()
    expected_count = int(max_id_input) if max_id_input.isdigit() else None
    
    print(f"\n开始检查乐曲数据文件: {json_file}")
    check_missing_songs(json_file, expected_count)
    
    input("\n检查完成，按Enter键退出...")