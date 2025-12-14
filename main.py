import os
import shutil
import tempfile
from tkinter import *
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageSequence
import queue
import threading
from tkinter import ttk

ui_queue = queue.Queue()

def optimize_gif(input_path, target_mb, progress_cb=None):
    start_size = os.path.getsize(input_path)
    target_bytes = int(target_mb * 1024 * 1024)

    img = Image.open(input_path)
    frames = [f.copy() for f in ImageSequence.Iterator(img)]

    MIN_COLORS = 8
    MIN_RESIZE = 0.25
    MAX_ATTEMPTS = 25

    colors = 256
    resize_factor = 1.0

    best_under = None
    best_under_size = 0
    best_under_params = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        temp_path = os.path.join(
            tempfile.gettempdir(), f"optimized_{attempt}.gif"
        )

        processed = []
        for f in frames:
            fr = f.resize(
                (int(f.width * resize_factor), int(f.height * resize_factor)),
                Image.LANCZOS
            )
            fr = fr.convert("P", palette=Image.ADAPTIVE, colors=colors)
            processed.append(fr)

        processed[0].save(
            temp_path,
            save_all=True,
            append_images=processed[1:],
            optimize=True,
            loop=0,
            disposal=2
        )

        size_now = os.path.getsize(temp_path)
        percent = size_progress_percent(start_size, size_now, target_bytes)

        if progress_cb:
            progress_cb(
                f"Attempt {attempt}: {size_now/1024/1024:.2f} MB",
                percent
            )

        # --- BELOW TARGET ---
        if size_now <= target_bytes:
            # store best under target
            if size_now > best_under_size:
                best_under = temp_path
                best_under_size = size_now
                best_under_params = (colors, resize_factor)

            # too small → try increasing quality
            if size_now < target_bytes * 0.85:
                colors = min(int(colors * 1.15), 256)
                resize_factor = min(resize_factor * 1.05, 1.0)
                continue

            # close enough → accept
            return temp_path

        # --- ABOVE TARGET ---
        else:
            # if we already have a valid result, rollback
            if best_under:
                print("↩ Rolling back to best under-target result")
                return best_under

            ratio = size_now / target_bytes

            # aggressive cut if far off
            if ratio > 3:
                colors = max(colors // 2, MIN_COLORS)
                resize_factor *= 0.75

            # moderate cut
            elif ratio > 1.5:
                colors = max(int(colors * 0.7), MIN_COLORS)
                resize_factor *= 0.9

            # fine cut
            else:
                colors = max(colors - 8, MIN_COLORS)
                resize_factor *= 0.95

            # impossible guard
            if colors <= MIN_COLORS and resize_factor <= MIN_RESIZE:
                break

    print("✔ Using best achieved under target")
    return best_under

def drop_event(event):
    input_path = event.data.strip("{}")
    target = float(target_entry.get().strip())

    status.set("Starting optimization…")
    progress_var.set(0)
    thread = threading.Thread(
        target=optimize_worker,
        args=(input_path, target),
        daemon=True
    )
    thread.start()


def optimize_worker(input_path, target):
    def progress_cb(msg, percent):
        ui_queue.put(("progress", msg, percent))


    try:
        optimized_path = optimize_gif(input_path, target, progress_cb)

        out_path = os.path.splitext(input_path)[0] + "_optimized.gif"
        shutil.copyfile(optimized_path, out_path)
        os.remove(optimized_path)

        ui_queue.put(("done", out_path))

    except Exception as e:
        ui_queue.put(("error", str(e)))


def poll_ui_queue():
    try:
        while True:
            item = ui_queue.get_nowait()
            kind = item[0]

            if kind == "progress":
                _, msg, percent = item
                status.set(msg)
                progress_var.set(percent)

            elif kind == "done":
                _, value = item
                status.set(f"Done! Saved as:\n{value}")
                progress_var.set(100)

            elif kind == "error":
                _, value = item
                status.set(f"Error:\n{value}")

    except queue.Empty:
        pass

    root.after(100, poll_ui_queue)


def size_progress_percent(start_size, current_size, target_size):
    if start_size <= target_size:
        return 100.0

    total_gap = start_size - target_size
    done_gap = start_size - current_size

    percent = (done_gap / total_gap) * 100
    return max(0.0, min(percent, 100.0))

# ===== UI =====
root = TkinterDnD.Tk()
progress_var = DoubleVar(value=0)
root.title("GIF Optimizer")

Label(root, text="Target Size (MB):").pack()

target_entry = Entry(root)
target_entry.insert(0, "1.5")
target_entry.pack()

frame = Label(
    root,
    text="\nDrop GIF Here\n",
    relief="solid",
    borderwidth=2,
    width=40,
    height=10
)
frame.pack(pady=10)

frame.drop_target_register(DND_FILES)
frame.dnd_bind("<<Drop>>", drop_event)
ttk.Progressbar(
    root,
    variable=progress_var,
    maximum=100,
    length=300
).pack(pady=5)

status = StringVar(value="Waiting for file…")
Label(root, textvariable=status, wraplength=350).pack()

root.after(100, poll_ui_queue)
root.mainloop()
