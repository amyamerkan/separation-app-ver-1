"""Build a self-contained Colab notebook from the reviewed Python modules."""
import ast
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cells = []


def markdown(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)})


def code(text):
    cells.append({"cell_type": "code", "metadata": {}, "source": text.splitlines(keepends=True),
                  "execution_count": None, "outputs": []})


markdown("""# DemucsLite V2 và HTDemucs — Colab huấn luyện, so sánh, xuất `.pth`

Chọn **Runtime → Change runtime type → GPU** trước khi chạy. Notebook tự tạo toàn bộ module, không cần upload các script riêng.

Hai nhánh: **DemucsLite V2 train từ đầu** để giữ tài nguyên thấp; **HTDemucs pretrained/fine-tune** để ưu tiên chất lượng trên server. HTDemucs_ft là ensemble cho suy luận, không gọi trực tiếp `model(x)` để train.

Checkpoint tốt nhất nghĩa là tốt nhất trong lần chạy theo **validation SNR**; chưa bảo đảm vượt baseline hoặc đạt chất lượng tối ưu tuyệt đối. Không chỉnh hyperparameter dựa trên test.

Dataset Drive của bạn: `musdb18hq.zip`, 22.656 GB (khoảng 21.1 GiB). Giải nén WAV cần thêm dung lượng lớn; notebook kiểm tra dung lượng trước. GPU Colab không bị giữ vĩnh viễn bằng việc chống sleep trên máy cá nhân.
""")
code("""import sys, subprocess, importlib.util, importlib.metadata
if sys.version_info >= (3, 13):
    raise RuntimeError('Notebook so sánh dùng Python 3.10–3.12 cho Demucs 4/NumPy 1.26. Khi đã kết nối runtime, mở Command Palette → Change runtime version → chọn 26.07 hoặc 26.04 (Python 3.12); phải chọn lại ở phiên mới. Nếu chỉ train V2, dùng main_v2_training_colab.ipynb trên runtime hiện tại.')
if importlib.util.find_spec('torch') is None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'torch==2.5.1', 'torchaudio==2.5.1'])
version = importlib.metadata.version('torch').split('+')[0]
try:
    matched = importlib.metadata.version('torchaudio').split('+')[0] == version
except importlib.metadata.PackageNotFoundError:
    matched = False
if not matched:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', f'torchaudio=={version}'])
# Cài NumPy trước khi import torch (torch cũng import NumPy).
loaded_numpy = getattr(sys.modules.get('numpy'), '__version__', None)
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'numpy>=1.26,<2',
                       'soundfile>=0.12,<0.14', 'demucs==4.0.1', 'tqdm>=4.66', 'pytest>=8'])
if loaded_numpy is not None and loaded_numpy != importlib.metadata.version('numpy'):
    raise RuntimeError('NumPy đã được kernel import trước khi đổi phiên bản. Restart session rồi chạy lại từ đầu.')
import torch
try:
    import torchaudio
    matched = torchaudio.__version__.split('+')[0] == torch.__version__.split('+')[0]
except (ImportError, OSError):
    matched = False
if not matched:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', f'torchaudio=={version}'])
    print('Đã sửa torch/torchaudio. Restart session rồi chạy lại từ đầu.')
    raise RuntimeError('Cần restart session sau khi đổi torchaudio.')
print('Python:', sys.version, 'PyTorch:', torch.__version__, 'CUDA:', torch.cuda.is_available())
if not torch.cuda.is_available():
    raise RuntimeError('Chọn GPU runtime. Không train dài trên CPU.')
print(torch.cuda.get_device_name(0))
""")
markdown("""## 1. Mount Drive và chọn nơi lưu

Drive mount có thể yêu cầu bạn đăng nhập/cấp quyền qua giao diện Google. Checkpoint đặt trong MyDrive; dữ liệu WAV sẽ giải nén vào `/content` để đọc nhanh hơn.
""")
code("""from google.colab import drive
drive.mount('/content/drive')
from pathlib import Path
import os
PROJECT = Path('/content/demucs_improved')
PROJECT.mkdir(exist_ok=True)
SAVE_ROOT = Path('/content/drive/MyDrive/DemucsImproved')
SAVE_ROOT.mkdir(parents=True, exist_ok=True)
os.chdir(PROJECT)
(PROJECT / 'audio_sep').mkdir(exist_ok=True)
(PROJECT / 'tests').mkdir(exist_ok=True)
print('Kết quả sẽ lưu vào:', SAVE_ROOT)
""")
markdown("""## 2. Code đã cải tiến

Các cell dưới chỉ ghi module. Có thể chỉnh code tại đây trước khi chạy; bản gốc không bị ghi đè.
""")
for path in sorted((ROOT / "audio_sep").glob("*.py")):
    code(f"%%writefile audio_sep/{path.name}\n" + path.read_text())
for path in sorted((ROOT / "tests").glob("test_*.py")):
    code(f"%%writefile tests/{path.name}\n" + path.read_text())
markdown("""## 3. Kiểm tra model/loss bằng dữ liệu tổng hợp

Các test này kiểm tra shape, gradient, stereo, im lặng, augmentation, checkpoint và nối các đoạn. Chúng **không chứng minh chất lượng tách nhạc**.
""")
code("""import subprocess, sys
subprocess.check_call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
""")
markdown("""## 4. Tìm ZIP trong Drive và giải nén trên Colab

Nếu folder đang ở **Shared with me**, chọn **Organize → Add shortcut → MyDrive**. Shortcut chỉ trỏ tới file/folder dùng chung, không sao chép 22 GB và không tính dung lượng file dùng chung vào quota MyDrive của bạn. Nếu thêm shortcut sau khi mount, chạy `drive.mount('/content/drive', force_remount=True)` rồi chạy lại cell này.

Code ưu tiên `ZIP_PATH` bạn đặt hoặc ZIP qua shortcut đã mount. Nếu tìm thấy 0 ZIP, nó đăng nhập Google và tải file dataset đã xác minh **trực tiếp vào ổ tạm `/content` của Colab**, không vào MyDrive và không về laptop. MyDrive chỉ lưu checkpoint. Tải từng chunk 8 MiB, kiểm tra quyền tải, metadata, dung lượng trống và checksum; ZIP hoàn chỉnh đã kiểm tra được dùng lại. Nếu tìm thấy nhiều ZIP, đặt `ZIP_PATH` rõ ràng.

Cả ZIP local lẫn WAV giải nén dùng dung lượng Colab; runtime vẫn cần đủ ổ đĩa. Phần giải nén kiểm tra dung lượng riêng sau khi đọc danh sách trong ZIP. Nếu có thể dùng shortcut đã mount, không cần lưu thêm một bản ZIP vào `/content`.
""")
code("""import os, shutil, zipfile, hashlib
DATASET_ARCHIVE_ID = '1leTZccqRToe17S7DcDXSRsqovnwNaZb5'
DATASET_ARCHIVE_NAME = 'musdb18hq.zip'
DATASET_ARCHIVE_SIZE = 22656664047  # metadata của file dataset đã xác minh
DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024
DISK_RESERVE_BYTES = 3 * 2**30

def complete_zip_verified(path, expected_size, expected_md5=None):
    path = Path(path)
    if not path.is_file() or path.stat().st_size != expected_size:
        return False
    if expected_md5:
        digest = hashlib.md5(usedforsecurity=False)  # checksum Drive, không dùng cho bảo mật
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK_BYTES), b''):
                digest.update(chunk)
        if digest.hexdigest().lower() != expected_md5.lower():
            return False
    if not zipfile.is_zipfile(path):
        return False
    if not expected_md5:
        # Nếu Drive không cung cấp MD5, kiểm tra CRC đầy đủ trước khi dùng cache.
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                return False
    return True

def download_dataset_zip():
    # Chỉ chạy nhánh này khi không có ZIP qua Drive mount/đường dẫn explicit.
    from google.colab import auth
    import google.auth
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from tqdm.auto import tqdm
    auth.authenticate_user()
    credentials, _ = google.auth.default()
    service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    metadata = service.files().get(
        fileId=DATASET_ARCHIVE_ID, supportsAllDrives=True,
        fields='id,name,size,md5Checksum,mimeType,capabilities(canDownload)',
    ).execute()
    if (metadata.get('id') != DATASET_ARCHIVE_ID
            or metadata.get('name') != DATASET_ARCHIVE_NAME
            or int(metadata.get('size', -1)) != DATASET_ARCHIVE_SIZE):
        raise RuntimeError('Metadata ZIP khác file dataset đã xác minh. Kiểm tra lại file ID/name/size.')
    if not metadata.get('capabilities', {}).get('canDownload', False):
        raise PermissionError('Tài khoản Google hiện tại không có quyền tải dataset. Đăng nhập tài khoản được chia sẻ file.')
    checksum = metadata.get('md5Checksum')
    local_zip = Path('/content') / DATASET_ARCHIVE_NAME
    partial = Path(str(local_zip) + '.part')
    if complete_zip_verified(local_zip, DATASET_ARCHIVE_SIZE, checksum):
        print('Dùng ZIP local đã xác minh:', local_zip)
        return local_zip
    if complete_zip_verified(partial, DATASET_ARCHIVE_SIZE, checksum):
        partial.replace(local_zip)
        print('Đã hoàn tất ZIP local từ file .part đã xác minh:', local_zip)
        return local_zip
    free = shutil.disk_usage('/content').free
    reclaimable_partial = partial.stat().st_size if partial.is_file() else 0
    print(f'ZIP cần {DATASET_ARCHIVE_SIZE/2**30:.1f} GiB trên Colab; còn trống {free/2**30:.1f} GiB')
    if free + reclaimable_partial < DATASET_ARCHIVE_SIZE + DISK_RESERVE_BYTES:
        raise RuntimeError('Thiếu dung lượng Colab để tải ZIP. Dùng shortcut đã mount hoặc runtime có ổ đĩa lớn hơn. Không cần copy ZIP vào MyDrive.')
    request = service.files().get_media(fileId=DATASET_ARCHIVE_ID, supportsAllDrives=True)
    # Stream vào .part, không giữ archive 22 GB trong RAM.
    with partial.open('wb') as handle, tqdm(total=DATASET_ARCHIVE_SIZE, unit='B', unit_scale=True,
                                          desc='Drive → /content') as progress:
        downloader = MediaIoBaseDownload(handle, request, chunksize=DOWNLOAD_CHUNK_BYTES)
        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=3)
            progress.update(handle.tell() - progress.n)
        handle.flush()
        os.fsync(handle.fileno())
    if not complete_zip_verified(partial, DATASET_ARCHIVE_SIZE, checksum):
        raise RuntimeError('ZIP tải về không đạt kiểm tra size/checksum/CRC. File .part chưa được dùng; chạy lại cell để tải lại.')
    partial.replace(local_zip)  # thay thế atomic sau khi đã kiểm tra hoàn chỉnh
    print('Đã tải và xác minh ZIP trên Colab:', local_zip)
    return local_zip

def resolve_zip_path(explicit_path=None):
    if explicit_path is not None:
        path = Path(explicit_path)
        if not path.is_file():
            raise FileNotFoundError('ZIP_PATH không tồn tại. Kiểm tra đường dẫn shortcut hoặc force_remount Drive.')
        return path
    matches = list(Path('/content/drive/MyDrive').rglob(DATASET_ARCHIVE_NAME))
    if len(matches) > 1:
        raise RuntimeError(f'Tìm thấy {len(matches)} ZIP. Đặt ZIP_PATH chính xác rồi chạy lại: {matches}')
    if matches:
        return matches[0]
    print('Không tìm thấy ZIP qua Drive mount. Tải bằng tài khoản được chia sẻ vào /content của Colab.')
    return download_dataset_zip()

# Giữ đường dẫn đã đặt ở cell trước; không cần hardcode tên folder MyDrive.
ZIP_PATH = resolve_zip_path(globals().get('ZIP_PATH'))
EXTRACT_ROOT = Path('/content/musdb18hq_data')
EXTRACT_ROOT.mkdir(exist_ok=True)
marker = EXTRACT_ROOT / '.extracted.json'
archive_signature = {'path': str(ZIP_PATH), 'size': ZIP_PATH.stat().st_size,
                     'mtime_ns': ZIP_PATH.stat().st_mtime_ns}
import json
if marker.exists():
    if json.loads(marker.read_text()) != archive_signature:
        raise RuntimeError('Thư mục đã chứa dataset khác. Chọn EXTRACT_ROOT mới.')
    print('Dùng dataset đã giải nén.')
else:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        members = [m for m in archive.infolist() if m.filename.lower().endswith('.wav')]
        if not members:
            raise RuntimeError('ZIP không có WAV.')
        remaining = sum(m.file_size for m in members
                        if not (EXTRACT_ROOT / m.filename).is_file()
                        or (EXTRACT_ROOT / m.filename).stat().st_size != m.file_size)
        free = shutil.disk_usage('/content').free
        print(f'Cần giải nén còn lại {remaining/2**30:.1f} GiB; còn trống {free/2**30:.1f} GiB')
        if free < remaining + 3 * 2**30:
            raise RuntimeError('Thiếu dung lượng Colab. Dùng runtime có nhiều disk hoặc dataset đã giải nén trên Drive.')
        from tqdm.auto import tqdm
        for member in tqdm(members, desc='Extract WAV'):
            destination = (EXTRACT_ROOT / member.filename).resolve()
            if not destination.is_relative_to(EXTRACT_ROOT.resolve()):
                raise RuntimeError('ZIP chứa đường dẫn không an toàn.')
            if destination.is_file() and destination.stat().st_size == member.file_size:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix('.wav.extracting')
            with archive.open(member) as src, temporary.open('wb') as dst:
                shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
            temporary.replace(destination)
    marker.write_text(json.dumps(archive_signature))
""")
markdown("""## 5. Audit và split chính thức

100 bài train gốc được chia **86 train + 14 validation** theo MUSDB; 50 bài test giữ riêng. Kiểm tra 5 WAV/bài, 44.1 kHz stereo, chiều dài và probe finite/mix–sum. Probe không thay thế kiểm tra mọi sample.

Riêng `test/PR - Oh No`, SigSep ghi nhận mixture kênh trái không bằng tổng stems. Dataset của bạn còn có residual kênh phải quan sát được khoảng 0,032/0,022 RMS ở hai probe; phần này được ghi là quan sát thêm, không được gán cho errata kênh phải của SigSep. Scanner mặc định áp dụng `warn_known_artistic_mix` cho đúng track test này: ghi cảnh báo cả hai kênh, giữ nguyên mixture/stems cùng đủ 50 bài test và lưu diagnostics. Ngoại lệ không áp dụng cho track khác, cùng tên trong train, sai metadata/shape hoặc sample không hữu hạn. Manifest ghi `known_issue`, `residual_policy` và residual probe lớn nhất từng kênh. Dùng `allow_known_errata=False` để từ chối residual trên cả hai kênh. [Errata chính thức cho kênh trái](https://sigsep.github.io/datasets/musdb.html#errata)
""")
code("""from audio_sep.data import scan_dataset
MANIFEST = PROJECT / 'manifest.json'
records = scan_dataset(EXTRACT_ROOT, MANIFEST)
from collections import Counter
print(Counter(r['subset'] for r in records))
shutil.copy2(MANIFEST, SAVE_ROOT / 'manifest.json')
shutil.copy2(PROJECT / 'manifest.audit.json', SAVE_ROOT / 'manifest.audit.json')
""")
markdown("""## 6. Chọn cấu hình huấn luyện

Batch 1 + accumulation 4 giảm VRAM. AMP dùng GradScaler để bỏ bước gradient lỗi và hạ scale; code ghi số bước bỏ qua, không cập nhật EMA/step khi bỏ bước. Với lỗi nonfinite ở run đang mở, đặt TRAIN_NO_AMP=True để resume bằng FP32. Chỉ đổi chế độ AMP/FP32 được resume cùng run; giữ nguyên manifest, segment, crops, LR và loss. Norm được tính float64 để tránh overflow khi mọi gradient vẫn hữu hạn. T4 có thể cần `TRAIN_SEGMENT=4`, hoặc tắt AMP nếu gặp gradient không hữu hạn. Đổi cấu hình phải dùng run name mới; resume chỉ dùng đúng cấu hình/dataset. Cần nhiều phiên Colab nếu train dài.

HTDemucs_ft dùng pretrained có dữ liệu bổ sung, nên mức điểm của nó không phải phép so sánh thuần kiến trúc với model train từ đầu trên 86 bài.
""")
code("""DO_TRAIN_LITE = True
DO_FINETUNE_HTDEMUCS = True
DO_TEST = True
RUN_NAME = 'v2_run_01'  # đổi tên cho một thí nghiệm khác
LITE_EPOCHS = 100
FINETUNE_EPOCHS = 20
TRAIN_SEGMENT = 6.0
TRAIN_CROPS = 32
VAL_CROPS = 8
LITE_DIR = SAVE_ROOT / RUN_NAME / 'lite'
HT_DIR = SAVE_ROOT / RUN_NAME / 'htdemucs_finetune'

TRAIN_WORKERS = 2
TRAIN_NO_AMP = False
""" + (ROOT / "colab_train_with_logs.py").read_text())
markdown("""## 7. Train DemucsLite V2

Mỗi epoch lưu `last.pth` và `history.csv`; khi validation SNR tăng lưu `best.pth` và xuất ngay `best_model.pth` chỉ chứa trọng số được chọn. Nếu phiên bị ngắt ở epoch sau, bản best đã xuất vẫn nằm trên Drive.
""")
code("""if DO_TRAIN_LITE:
    train_run('lite', LITE_DIR, LITE_EPOCHS, 3e-4, 15)
""")
markdown("""## 8. Fine-tune HTDemucs

Dùng một backbone `htdemucs`, không train ensemble `htdemucs_ft`. LR thấp 1e-5. Điểm pretrained trước fine-tune là ứng viên epoch 0 và được xuất ngay thành `best_model.pth`, nên nếu các epoch sau kém hơn hoặc phiên bị ngắt thì file best giữ pretrained. Trọng số từ bước tải chính thức mới được nạp với chế độ tương thích PyTorch 2.6; không nạp checkpoint lạ.
""")
code("""if DO_FINETUNE_HTDEMUCS:
    train_run('pretrained', HT_DIR, FINETUNE_EPOCHS, 1e-5, 5)
""")
markdown("""## 9. So sánh toàn bộ 50 bài test

SNR và SI-SDR báo riêng, lấy median các cửa sổ 1 giây có tín hiệu trong từng bài, rồi lấy mean theo bài/stem. Không gọi các số này là BSS Eval SDR trong paper. Test chỉ dùng để báo kết quả sau khi khóa cấu hình.

Thêm checkpoint cũ vào `OLD_CHECKPOINT` để so với bản gốc. Bản gốc split random 85/15 khác split hiện tại: chỉ dùng test cho phép so sánh với nó. Đánh giá ensemble 4 model và nhiều shifts tốn thời gian hơn.
""")
code("""OLD_CHECKPOINT = None  # Path('/content/drive/MyDrive/.../demucs_lite_best.pth')
REPORT_DIR = SAVE_ROOT / RUN_NAME / 'evaluation'
REPORT_DIR.mkdir(parents=True, exist_ok=True)
jobs = [('htdemucs_ft', ['--official', 'htdemucs_ft'])]
if (LITE_DIR / 'best_model.pth').exists():
    jobs.append(('lite_v2', ['--checkpoint', str(LITE_DIR / 'best_model.pth')]))
if (HT_DIR / 'best_model.pth').exists():
    jobs.append(('htdemucs_finetune', ['--checkpoint', str(HT_DIR / 'best_model.pth')]))
if OLD_CHECKPOINT:
    jobs.append(('lite_original', ['--legacy-checkpoint', str(OLD_CHECKPOINT)]))
if DO_TEST:
    for name, options in jobs:
        subprocess.check_call([sys.executable, '-m', 'audio_sep.evaluate', '--manifest', str(MANIFEST),
                               '--subset', 'test', '--output', str(REPORT_DIR / f'{name}.json'), *options])
    for name, _ in jobs:
        report = json.loads((REPORT_DIR / f'{name}.json').read_text())
        print(name, json.dumps(report['summary'], ensure_ascii=False))
""")
markdown("""## 10. Nghe thử trên cùng một bài

Float WAV giữ biên độ để đánh giá; phát nghe chỉ normalize cho player. Không normalize từng stem rồi dùng file đã normalize để tính metric. Muốn so nhiều model, đổi `MODE` và cùng `INPUT_AUDIO`.
""")
code("""INPUT_AUDIO = Path(next(r['path'] for r in records if r['subset']=='test')) / 'mixture.wav'
MODE = 'htdemucs_ft'  # 'htdemucs_ft' | 'lite_v2' | 'htdemucs_finetune'
OUTPUT_AUDIO = SAVE_ROOT / RUN_NAME / 'listening' / MODE
options = ['--official', MODE] if MODE == 'htdemucs_ft' else [
    '--checkpoint', str((LITE_DIR if MODE == 'lite_v2' else HT_DIR) / 'best_model.pth')]
subprocess.check_call([sys.executable, '-m', 'audio_sep.inference', str(INPUT_AUDIO),
                       '--output', str(OUTPUT_AUDIO), *options])
from IPython.display import Audio, display
import soundfile as sf
for source in ('vocals','drums','bass','other'):
    audio, sr = sf.read(OUTPUT_AUDIO / f'{source}.wav', always_2d=True)
    print(source)
    display(Audio(audio[:30*sr].T, rate=sr))
""")
markdown("""## 11. Export best `.pth` và download

File Drive được lưu kể cả khi trình duyệt đóng. Đừng thay thẳng checkpoint V2 vào API cũ: loader phải dựng đúng architecture/config và source order; xem `audio_sep.inference.load_checkpoint`. Bản HTDemucs export chứa constructor config để load không cần tải pretrained lại, nhưng cần cài thư viện Demucs.
""")
code("""from audio_sep.train import export_best
for directory in (LITE_DIR, HT_DIR):
    if (directory / 'best.pth').exists():
        export_best(directory)  # cũng dùng được nếu dừng train sau một epoch
        print('Đã xuất:', directory / 'best_model.pth')
DOWNLOAD_CHECKPOINTS = False  # đổi True để tải về máy; file vẫn có sẵn trên Drive
if DOWNLOAD_CHECKPOINTS:
    from google.colab import files
    for directory in (LITE_DIR, HT_DIR):
        if (directory / 'best_model.pth').exists():
            files.download(str(directory / 'best_model.pth'))
""")
markdown("""Nguồn: [Demucs chính thức](https://github.com/facebookresearch/demucs), [code suy luận](https://github.com/facebookresearch/demucs/blob/main/demucs/apply.py), [MUSDB validation split](https://github.com/sigsep/sigsep-mus-db/blob/master/musdb/configs/mus.yaml), [Hybrid Demucs paper](https://arxiv.org/abs/2111.03600).
""")
notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}, "colab": {"provenance": []}, "accelerator": "GPU"}, "cells": cells}


def write_notebook(document, filename):
    for index, cell in enumerate(document["cells"]):
        cell["id"] = f"demucs-{index:03d}"
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            if source.startswith("%%writefile"):
                source = source.split("\n", 1)[1]
            ast.parse(source)
    output = ROOT / filename
    output.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n")
    print(f"Built {output} ({len(document['cells'])} cells)")


write_notebook(notebook, "main_improved_colab.ipynb")
v2_only = copy.deepcopy(notebook)
v2_only["cells"][0]["source"] = ("""# Huấn luyện DemucsLite V2 trên Colab

Bản này mặc định **chỉ train DemucsLite V2** và nghe checkpoint V2 vừa xuất. Giữ PyTorch/NumPy của runtime Colab hiện tại, gồm Python 3.13 trở lên; không cài Demucs, torchaudio hoặc ép NumPy xuống 1.x. Chạy 36 test cho Lite, không chạy hai test HTDemucs. Chọn GPU trước khi chạy.

Fine-tune HTDemucs và đánh giá toàn bộ 50 bài test được tắt. Để dùng HTDemucs, mở notebook `main_improved_colab.ipynb` trong môi trường legacy riêng; notebook đó hướng dẫn chọn runtime Python 3.12. Chỉ đánh giá test sau khi đã khóa cấu hình.

""" + "Checkpoint tốt nhất" + "".join(notebook["cells"][0]["source"]).split("Checkpoint tốt nhất", 1)[1]).splitlines(keepends=True)
v2_only["cells"][1]["source"] = """import sys, os, subprocess, importlib.util, importlib.metadata
# Dùng PyTorch CUDA có sẵn trên Colab, không thay bằng wheel khác.
if importlib.util.find_spec('torch') is None:
    raise RuntimeError('Runtime này chưa có PyTorch. Chọn GPU runtime Colab có PyTorch sẵn.')
loaded_numpy = getattr(sys.modules.get('numpy'), '__version__', None)
requirements = {
    'numpy': ('numpy>=1.26', (1, 26)),
    'soundfile': ('soundfile>=0.12', (0, 12)),
    'tqdm': ('tqdm>=4.66', (4, 66)),
}
missing_or_old = []
for package, (specification, minimum) in requirements.items():
    try:
        installed = importlib.metadata.version(package)
        meets_minimum = tuple(int(part) for part in installed.split('.')[:2]) >= minimum
    except (importlib.metadata.PackageNotFoundError, ValueError):
        meets_minimum = False
    if not meets_minimum:
        missing_or_old.append(specification)
if missing_or_old:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *missing_or_old])
if loaded_numpy is not None and loaded_numpy != importlib.metadata.version('numpy'):
    raise RuntimeError('NumPy đã được kernel import trước khi nâng phiên bản. Restart session rồi chạy lại từ đầu.')
import numpy as np
import torch
import soundfile as sf
# Kiểm tra bridge NumPy ↔ PyTorch thay vì chặn theo phiên bản Python.
probe = np.zeros((2, 16), dtype=np.float32)
assert np.array_equal(torch.from_numpy(probe).numpy(), probe)
print('Python:', sys.version, 'PyTorch:', torch.__version__, 'NumPy:', np.__version__,
      'SoundFile:', sf.__version__, 'CUDA:', torch.cuda.is_available())
if not torch.cuda.is_available():
    raise RuntimeError('Chọn GPU runtime. Không train dài trên CPU.')
print(torch.cuda.get_device_name(0))
""".splitlines(keepends=True)
for cell in v2_only["cells"]:
    source = "".join(cell["source"])
    if cell["cell_type"] == "code" and not source.startswith("%%writefile"):
        source = source.replace("DO_FINETUNE_HTDEMUCS = True", "DO_FINETUNE_HTDEMUCS = False")
        source = source.replace("DO_TEST = True", "DO_TEST = False")
        source = source.replace("MODE = 'htdemucs_ft'  #", "MODE = 'lite_v2'  #")
        if "'unittest', 'discover'" in source:
            source = """import os, subprocess, sys
# 29 test data/inference/model/loss/evaluation, 5 test optimizer/AMP và 2 test pipeline Lite.
# Không chạy test constructor/checkpoint/baseline HTDemucs.
LITE_TESTS = [
    'test_data', 'test_inference', 'test_model_losses', 'test_evaluate',
    'test_training.GradientStepTest',
    'test_training.TrainingTest.test_latest_best_export_survives_interruption_in_later_epoch',
    'test_training.TrainingTest.test_train_resume_export_and_full_track_evaluation',
]
test_environment = os.environ.copy()
test_environment['PYTHONPATH'] = os.pathsep.join((str(PROJECT / 'tests'), str(PROJECT)))
subprocess.check_call([sys.executable, '-m', 'unittest', *LITE_TESTS, '-v'],
                      cwd=PROJECT, env=test_environment)
"""
    cell["source"] = source.splitlines(keepends=True)
write_notebook(v2_only, "main_v2_training_colab.ipynb")
