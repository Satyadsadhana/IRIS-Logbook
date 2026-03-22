import os
import csv
import json
import base64
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory

import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image
from facenet_pytorch import MTCNN

app = Flask(__name__)

# =========================
# Config
# =========================
MODEL_DIR = os.path.join(app.root_path, "model")
LABEL_JSON = os.path.join(MODEL_DIR, "shortterm.json")
MODEL_PATH = os.path.join(MODEL_DIR, "best_face_new.pth")
LOG_FILE = os.path.join(app.root_path, "log.csv")

CONFIDENCE_THRESHOLD = 0.75

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = None
idx_to_name = {}

# =========================
# Load label mapping
# =========================
try:
    if not os.path.exists(LABEL_JSON):
        raise FileNotFoundError(f"File label mapping tidak ditemukan: {LABEL_JSON}")

    with open(LABEL_JSON, "r", encoding="utf-8") as f:
        class_mapping = json.load(f)

    idx_to_name = {int(v): k for k, v in class_mapping.items()}
    app.logger.info(f"Label mapping loaded: {len(idx_to_name)} classes")

except Exception as e:
    app.logger.error(f"Gagal load label mapping: {e}")
    class_mapping = {}
    idx_to_name = {}

# =========================
# Load full model
# =========================
try:
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"File model tidak ditemukan: {MODEL_PATH}")

    model = torch.load(
        MODEL_PATH,
        map_location=device,
        weights_only=False
    )
    model.to(device)
    model.eval()
    app.logger.info("Full model loaded successfully.")

except Exception as e:
    app.logger.error(f"Error loading full model: {e}")
    model = None

# =========================
# MTCNN Face Detector
# =========================
mtcnn = MTCNN(
    image_size=299,
    margin=20,
    min_face_size=60,
    thresholds=[0.6, 0.7, 0.7],
    keep_all=False,
    post_process=False,   # output tensor uint8 [C, H, W], range 0-255
    device=device
)

# =========================
# Image transform
# =========================
# post_process=False → MTCNN output tensor uint8, bukan PIL
# jadi TIDAK pakai ToTensor, langsung normalize setelah div(255)
normalize = transforms.Normalize(
    mean=[0.485, 0.456, 0.406],
    std =[0.229, 0.224, 0.225]
)

# =========================
# Routes
# =========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/images/<path:filename>")
def serve_image(filename):
    images_dir = os.path.join(app.root_path, "images")
    return send_from_directory(images_dir, filename)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "model_loaded": model is not None,
        "num_classes": len(idx_to_name),
        "device": str(device)
    })


@app.route("/logs", methods=["GET"])
def get_logs():
    entries = []
    if os.path.isfile(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip().lower() in ("name", "nama"):
                    continue
                if len(row) >= 3:
                    entries.append({
                        "name":       row[0].strip(),
                        "confidence": row[1].strip(),
                        "datetime":   row[2].strip()
                    })
                elif len(row) == 2:
                    entries.append({
                        "name":       row[0].strip(),
                        "confidence": "",
                        "datetime":   row[1].strip()
                    })
    entries.reverse()
    return jsonify({"success": True, "logs": entries})


@app.route("/recognize", methods=["POST"])
def recognize():
    try:
        if model is None:
            return jsonify({
                "success": False,
                "message": "Model belum berhasil diload. Pastikan file .pth adalah full model hasil torch.save(model, ...)."
            }), 500

        data = request.get_json(silent=True)
        if not data or "image" not in data:
            return jsonify({
                "success": False,
                "message": "No image provided"
            }), 400

        image_b64 = data["image"]
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            return jsonify({
                "success": False,
                "message": "Gagal decode base64 image"
            }), 400

        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({
                "success": False,
                "message": "Format gambar tidak valid"
            }), 400

        # BGR -> RGB -> PIL (MTCNN butuh PIL RGB)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_pil = Image.fromarray(frame_rgb)

        # deteksi & crop wajah dengan MTCNN
        # output: tensor uint8 [C, H, W] jika wajah ditemukan, None jika tidak
        face_tensor, prob = mtcnn(frame_pil, return_prob=True)

        if face_tensor is None:
            return jsonify({
                "success": False,
                "message": "Wajah tidak terdeteksi"
            }), 200

        app.logger.debug(f"MTCNN detection prob: {prob:.4f}")

        # konversi uint8 [0-255] → float32 [0-1] → normalize ImageNet
        # unsqueeze(0) untuk tambah batch dimension: [C,H,W] → [1,C,H,W]
        input_tensor = normalize(face_tensor.float().div(255)).unsqueeze(0).to(device)

        with torch.no_grad():
            outputs = model(input_tensor)
            probs = torch.softmax(outputs, dim=1)
            conf, predicted = torch.max(probs, dim=1)

            pred_idx = int(predicted.item())
            confidence = float(conf.item())

        if confidence < CONFIDENCE_THRESHOLD:
            return jsonify({
                "success": False,
                "message": f"Wajah tidak dikenali (confidence terlalu rendah: {confidence:.2%})"
            }), 200

        person_name = idx_to_name.get(pred_idx, "Unknown")
        dt_string = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["Name", "Confidence", "Datetime"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists or os.path.getsize(LOG_FILE) == 0:
                writer.writeheader()
            writer.writerow({
                "Name": person_name,
                "Confidence": f"{confidence:.4f}",
                "Datetime": dt_string
            })

        return jsonify({
            "success": True,
            "name": person_name,
            "confidence": round(confidence, 4),
            "datetime": dt_string,
            "message": f"Kehadiran {person_name} berhasil dicatat."
        })

    except Exception as e:
        app.logger.exception("Terjadi error saat recognize")
        return jsonify({
            "success": False,
            "message": f"Terjadi kesalahan: {str(e)}"
        }), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)