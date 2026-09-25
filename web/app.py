from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import os
import subprocess
import sys
import uuid


app = FastAPI()

os.makedirs("input", exist_ok=True)
os.makedirs("output", exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory="web/static"),
    name="static",
)


PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Formochka3D</title>

    <style>
        * {
            box-sizing: border-box;
        }

        html,
        body {
            margin: 0;
            padding: 0;
            min-height: 100%;
        }

        body {
            font-family: Arial, Helvetica, sans-serif;
            background: #fff7f1;
            color: #332b28;
        }

        .page-shell {
            width: 100%;
            max-width: 1100px;
            min-height: 100vh;
            margin: 0 auto;
            position: relative;

            background-image: url("/static/background.png");
            background-repeat: no-repeat;
            background-position: top center;
            background-size: 100% auto;

            padding: 560px 32px 90px;
        }

        .topbar {
            width: 100%;
            background: rgba(255, 250, 246, 0.98);
            border-bottom: 1px solid #eadbd0;
            box-shadow: 0 3px 14px rgba(91, 56, 38, 0.05);
            position: relative;
            z-index: 20;
        }

        .topbar-inner {
            width: 100%;
            max-width: 1100px;
            min-height: 86px;
            margin: 0 auto;
            padding: 12px 32px;

            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 28px;
        }

        .site-logo {
            display: flex;
            align-items: center;
            flex-shrink: 0;
        }

        .site-logo img {
            display: block;
            width: 265px;
            height: auto;
            object-fit: contain;
        }

        .topnav {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 28px;
            flex-wrap: wrap;
        }

        .topnav a {
            color: #5e4d45;
            text-decoration: none;
            font-size: 15px;
            font-weight: 700;
            white-space: nowrap;
            transition: color 0.15s ease;
        }

        .topnav a:hover {
            color: #e8844e;
        }

        .modes {
            width: 100%;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 28px;
            align-items: start;
        }

        .mode-card {
            background: rgba(255, 255, 255, 0.96);
            border-radius: 30px;
            padding: 31px;
            box-shadow: 0 16px 45px rgba(107, 65, 40, 0.10);
            backdrop-filter: blur(3px);
        }

        .mode-card h2 {
            margin: 0 0 12px;
            text-align: center;
            font-size: 29px;
            line-height: 1.2;
            color: #332b28;
        }

        .mode-description {
            min-height: 50px;
            margin-bottom: 24px;
            text-align: center;
            color: #77675f;
            font-size: 16px;
            line-height: 1.45;
        }

        .upload-area {
            padding: 27px 22px;
            border: 2px dashed #e4d4ca;
            border-radius: 22px;
            background: rgba(255, 250, 246, 0.90);
            text-align: center;
        }

        .example-image {
            display: block;
            width: 100%;
            max-width: 430px;
            height: auto;
            margin: 0 auto 18px;
            border-radius: 18px;
            box-shadow: 0 8px 22px rgba(107, 65, 40, 0.08);
        }

        .file-input {
            display: none;
        }

        .main-button {
            display: block;
            width: 100%;
            padding: 18px;
            border: none;
            border-radius: 17px;
            background: linear-gradient(135deg, #ef975f, #e77e43);
            color: white;
            font-size: 18px;
            font-weight: 700;
            text-align: center;
            cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }

        .main-button:hover,
        .create-button:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(204, 112, 61, 0.22);
        }

        .file-note {
            margin-top: 13px;
            color: #998a82;
            font-size: 13px;
        }

        .preview-box {
            display: none;
            margin-top: 23px;
            text-align: center;
        }

        .preview-box h3 {
            margin: 0 0 14px;
            font-size: 20px;
            color: #413631;
        }

        .preview-box img {
            display: block;
            max-width: 100%;
            max-height: 330px;
            margin: auto;
            border: 1px solid #eee5df;
            border-radius: 18px;
            background: white;
            transform: scaleX(-1);
        }

        .settings-box {
            display: none;
            margin-top: 22px;
            padding: 22px;
            border-radius: 20px;
            background: #fff7f2;
        }

        .setting {
            margin-bottom: 29px;
        }

        .setting:last-child {
            margin-bottom: 0;
        }

        .setting-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            margin-bottom: 12px;
            font-size: 17px;
            font-weight: 700;
        }

        .setting-value {
            flex-shrink: 0;
            padding: 7px 12px;
            border-radius: 11px;
            background: white;
            color: #df7540;
            font-weight: 800;
        }

        input[type="range"] {
            width: 100%;
            accent-color: #e8844e;
            cursor: pointer;
        }

        .range-labels {
            display: flex;
            justify-content: space-between;
            margin-top: 5px;
            color: #93817a;
            font-size: 13px;
        }

        .create-button {
            display: none;
            width: 100%;
            margin-top: 20px;
            padding: 18px;
            border: none;
            border-radius: 17px;
            background: linear-gradient(135deg, #ef975f, #e77e43);
            color: white;
            font-size: 18px;
            font-weight: 700;
            cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }

        .another-button {
            display: none;
            margin-top: 16px;
            color: #79665d;
            text-decoration: underline;
            text-align: center;
            cursor: pointer;
        }

        .status {
            display: none;
            margin-top: 15px;
            text-align: center;
            color: #765e53;
        }

        .error {
            display: none;
            margin-top: 15px;
            padding: 12px;
            border-radius: 12px;
            background: #fff0ed;
            color: #9b3c2f;
            text-align: center;
        }


        .instruction-section {
            width: 100%;
            max-width: 1100px;
            margin: 28px auto 0;
            padding: 0 0 70px;
            scroll-margin-top: 24px;
        }

        .instruction-card {
            width: 100%;
            background: rgba(255, 255, 255, 0.96);
            border-radius: 30px;
            padding: 18px;
            box-shadow: 0 16px 45px rgba(107, 65, 40, 0.10);
        }

        .instruction-card img {
            display: block;
            width: 100%;
            height: auto;
            border-radius: 22px;
        }

        @media(max-width: 850px) {
            .page-shell {
                min-height: 1300px;
                padding: 52vw 18px 70px;
            }

            .topbar-inner {
                padding: 10px 18px;
                min-height: 76px;
            }

            .site-logo img {
                width: 225px;
            }

            .topnav {
                gap: 16px;
            }

            .topnav a {
                font-size: 14px;
            }

            .modes {
                grid-template-columns: 1fr;
                gap: 22px;
            }
        }

        @media(max-width: 520px) {
            .page-shell {
                padding-left: 12px;
                padding-right: 12px;
            }

            .topbar-inner {
                align-items: flex-start;
                gap: 10px;
                padding: 10px 14px 12px;
            }

            .site-logo img {
                width: 178px;
            }

            .topnav {
                gap: 9px 13px;
                padding-top: 7px;
            }

            .topnav a {
                font-size: 12px;
            }

            .mode-card {
                padding: 22px;
            }

            .mode-card h2 {
                font-size: 24px;
            }
        }
    </style>
</head>

<body>

<header class="topbar">
    <div class="topbar-inner">

        <a class="site-logo" href="/" aria-label="Formochka3D — главная">
            <img src="/static/logo.png" alt="Formochka3D">
        </a>

        <nav class="topnav">
            <a href="#generator">Создать STL</a>
            <a href="#instruction">Инструкция</a>
            <a href="#">Готовые формочки</a>
            <a href="#">Связаться</a>
        </nav>

    </div>
</header>

<div class="page-shell">

    <div class="modes" id="generator">

        <div class="mode-card">
            <h2>Картинка → формочка</h2>

            <div class="mode-description">
                Загрузите фотографию, рисунок или готовый силуэт.
            </div>

            <div class="upload-area">
                <img
                    class="example-image"
                    src="/static/example_image.png"
                    alt="Пример: изображение → формочка → готовый результат"
                >

                <label
                    for="imageFile"
                    class="main-button"
                    id="imageUploadLabel"
                >
                    Загрузить изображение
                </label>

                <div class="file-note">
                    JPG, PNG, WEBP
                </div>
            </div>

            <input
                id="imageFile"
                class="file-input"
                type="file"
                accept="image/*"
            >

            <div
                class="preview-box"
                id="imagePreviewBox"
            >
                <h3>Проверьте контур</h3>
                <img
                    id="imagePreview"
                    alt="Предпросмотр контура"
                >
            </div>

            <div
                class="settings-box"
                id="imageSettings"
            >
                <div class="setting">
                    <div class="setting-title">
                        <span>Размер формочки</span>
                        <span
                            class="setting-value"
                            id="imageSizeValue"
                        >
                            100 мм
                        </span>
                    </div>

                    <input
                        id="imageSize"
                        type="range"
                        min="40"
                        max="200"
                        step="1"
                        value="100"
                    >

                    <div class="range-labels">
                        <span>40 мм</span>
                        <span>200 мм</span>
                    </div>
                </div>

                <div class="setting">
                    <div class="setting-title">
                        <span>Высота режущей части</span>
                        <span
                            class="setting-value"
                            id="imageHeightValue"
                        >
                            10 мм
                        </span>
                    </div>

                    <input
                        id="imageHeight"
                        type="range"
                        min="5"
                        max="30"
                        step="1"
                        value="10"
                    >

                    <div class="range-labels">
                        <span>5 мм</span>
                        <span>30 мм</span>
                    </div>
                </div>
            </div>

            <button
                class="create-button"
                id="imageCreateButton"
            >
                Подтвердить и создать STL
            </button>

            <div
                class="status"
                id="imageStatus"
            >
                Создаём STL...
            </div>

            <div
                class="error"
                id="imageError"
            ></div>

            <div
                class="another-button"
                id="imageAnotherButton"
            >
                Выбрать другое изображение
            </div>
        </div>


        <div class="mode-card">
            <h2>Буква или цифра → формочка</h2>

            <div class="mode-description">
                Для букв и цифр сохраняются внутренние отверстия и перемычки.
            </div>

            <div class="upload-area">
                <img
                    class="example-image"
                    src="/static/example_text.png"
                    alt="Пример: буква или цифра → формочка → готовый результат"
                >

                <label
                    for="textFile"
                    class="main-button"
                    id="textUploadLabel"
                >
                    Загрузить букву или цифру
                </label>

                <div class="file-note">
                    JPG, PNG, WEBP
                </div>
            </div>

            <input
                id="textFile"
                class="file-input"
                type="file"
                accept="image/*"
            >

            <div
                class="preview-box"
                id="textPreviewBox"
            >
                <h3>Проверьте контур</h3>
                <img
                    id="textPreview"
                    alt="Предпросмотр буквы или цифры"
                >
            </div>

            <div
                class="settings-box"
                id="textSettings"
            >
                <div class="setting">
                    <div class="setting-title">
                        <span>Размер формочки</span>
                        <span
                            class="setting-value"
                            id="textSizeValue"
                        >
                            100 мм
                        </span>
                    </div>

                    <input
                        id="textSize"
                        type="range"
                        min="40"
                        max="200"
                        step="1"
                        value="100"
                    >

                    <div class="range-labels">
                        <span>40 мм</span>
                        <span>200 мм</span>
                    </div>
                </div>

                <div class="setting">
                    <div class="setting-title">
                        <span>Высота режущей части</span>
                        <span
                            class="setting-value"
                            id="textHeightValue"
                        >
                            10 мм
                        </span>
                    </div>

                    <input
                        id="textHeight"
                        type="range"
                        min="5"
                        max="30"
                        step="1"
                        value="10"
                    >

                    <div class="range-labels">
                        <span>5 мм</span>
                        <span>30 мм</span>
                    </div>
                </div>
            </div>

            <button
                class="create-button"
                id="textCreateButton"
            >
                Подтвердить и создать STL
            </button>

            <div
                class="status"
                id="textStatus"
            >
                Создаём STL...
            </div>

            <div
                class="error"
                id="textError"
            ></div>

            <div
                class="another-button"
                id="textAnotherButton"
            >
                Выбрать другую букву или цифру
            </div>
        </div>

    </div>

    <section
        class="instruction-section"
        id="instruction"
    >
        <div class="instruction-card">
            <img
                src="/static/instruction.png"
                alt="Инструкция Formochka3D"
            >
        </div>
    </section>

</div>


<script>
    let currentImageFile = "";
    let currentImageName = "";

    let currentTextFile = "";
    let currentTextName = "";


    const imageSize =
        document.getElementById("imageSize");

    const imageHeight =
        document.getElementById("imageHeight");

    const textSize =
        document.getElementById("textSize");

    const textHeight =
        document.getElementById("textHeight");


    imageSize.addEventListener(
        "input",
        function () {
            document.getElementById(
                "imageSizeValue"
            ).textContent =
                imageSize.value + " мм";
        }
    );


    imageHeight.addEventListener(
        "input",
        function () {
            document.getElementById(
                "imageHeightValue"
            ).textContent =
                imageHeight.value + " мм";
        }
    );


    textSize.addEventListener(
        "input",
        function () {
            document.getElementById(
                "textSizeValue"
            ).textContent =
                textSize.value + " мм";
        }
    );


    textHeight.addEventListener(
        "input",
        function () {
            document.getElementById(
                "textHeightValue"
            ).textContent =
                textHeight.value + " мм";
        }
    );


    const imageFile =
        document.getElementById("imageFile");


    imageFile.addEventListener(
        "change",
        async function () {

            if (!imageFile.files.length) {
                return;
            }

            const label =
                document.getElementById(
                    "imageUploadLabel"
                );

            const error =
                document.getElementById(
                    "imageError"
                );

            error.style.display = "none";
            label.textContent =
                "Обрабатываем изображение...";

            const formData =
                new FormData();

            formData.append(
                "file",
                imageFile.files[0]
            );

            try {
                const response =
                    await fetch(
                        "/prepare-image",
                        {
                            method: "POST",
                            body: formData
                        }
                    );

                const data =
                    await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.error ||
                        "Ошибка обработки изображения"
                    );
                }

                currentImageFile =
                    data.file;

                currentImageName =
                    data.name;

                document.getElementById(
                    "imagePreview"
                ).src =
                    "/preview-image?t=" +
                    Date.now();

                document.getElementById(
                    "imagePreviewBox"
                ).style.display =
                    "block";

                document.getElementById(
                    "imageSettings"
                ).style.display =
                    "block";

                document.getElementById(
                    "imageCreateButton"
                ).style.display =
                    "block";

                document.getElementById(
                    "imageAnotherButton"
                ).style.display =
                    "block";

                label.style.display =
                    "none";
            }

            catch (e) {
                label.style.display =
                    "block";

                label.textContent =
                    "Загрузить изображение";

                error.textContent =
                    e.message;

                error.style.display =
                    "block";
            }
        }
    );


    document.getElementById(
        "imageCreateButton"
    ).addEventListener(
        "click",
        async function () {

            const status =
                document.getElementById(
                    "imageStatus"
                );

            const error =
                document.getElementById(
                    "imageError"
                );

            error.style.display = "none";
            status.style.display = "block";

            const formData =
                new FormData();

            formData.append(
                "file",
                currentImageFile
            );

            formData.append(
                "name",
                currentImageName
            );

            formData.append(
                "size",
                imageSize.value
            );

            formData.append(
                "height",
                imageHeight.value
            );

            try {
                const response =
                    await fetch(
                        "/create-image",
                        {
                            method: "POST",
                            body: formData
                        }
                    );

                if (!response.ok) {
                    const data =
                        await response.json();

                    throw new Error(
                        data.error ||
                        "Не удалось создать STL"
                    );
                }

                const blob =
                    await response.blob();

                const url =
                    URL.createObjectURL(
                        blob
                    );

                const a =
                    document.createElement(
                        "a"
                    );

                a.href = url;

                a.download =
                    currentImageName +
                    ".stl";

                document.body.appendChild(
                    a
                );

                a.click();
                a.remove();

                URL.revokeObjectURL(
                    url
                );
            }

            catch (e) {
                error.textContent =
                    e.message;

                error.style.display =
                    "block";
            }

            status.style.display =
                "none";
        }
    );


    document.getElementById(
        "imageAnotherButton"
    ).addEventListener(
        "click",
        function () {

            imageFile.value = "";
            currentImageFile = "";
            currentImageName = "";

            document.getElementById(
                "imagePreviewBox"
            ).style.display =
                "none";

            document.getElementById(
                "imageSettings"
            ).style.display =
                "none";

            document.getElementById(
                "imageCreateButton"
            ).style.display =
                "none";

            document.getElementById(
                "imageAnotherButton"
            ).style.display =
                "none";

            document.getElementById(
                "imageError"
            ).style.display =
                "none";

            const label =
                document.getElementById(
                    "imageUploadLabel"
                );

            label.style.display =
                "block";

            label.textContent =
                "Загрузить изображение";
            label.scrollIntoView({behavior: "smooth", block: "center"});
        }
    );


    const textFile =
        document.getElementById(
            "textFile"
        );


    textFile.addEventListener(
        "change",
        async function () {

            if (!textFile.files.length) {
                return;
            }

            const label =
                document.getElementById(
                    "textUploadLabel"
                );

            const error =
                document.getElementById(
                    "textError"
                );

            error.style.display = "none";

            label.textContent =
                "Обрабатываем изображение...";

            const formData =
                new FormData();

            formData.append(
                "file",
                textFile.files[0]
            );

            try {
                const response =
                    await fetch(
                        "/prepare-text",
                        {
                            method: "POST",
                            body: formData
                        }
                    );

                const data =
                    await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.error ||
                        "Ошибка обработки буквы или цифры"
                    );
                }

                currentTextFile =
                    data.file;

                currentTextName =
                    data.name;

                document.getElementById(
                    "textPreview"
                ).src =
                    "/preview-text?t=" +
                    Date.now();

                document.getElementById(
                    "textPreviewBox"
                ).style.display =
                    "block";

                document.getElementById(
                    "textSettings"
                ).style.display =
                    "block";

                document.getElementById(
                    "textCreateButton"
                ).style.display =
                    "block";

                document.getElementById(
                    "textAnotherButton"
                ).style.display =
                    "block";

                label.style.display =
                    "none";
            }

            catch (e) {
                label.style.display =
                    "block";

                label.textContent =
                    "Загрузить букву или цифру";

                error.textContent =
                    e.message;

                error.style.display =
                    "block";
            }
        }
    );


    document.getElementById(
        "textCreateButton"
    ).addEventListener(
        "click",
        async function () {

            const status =
                document.getElementById(
                    "textStatus"
                );

            const error =
                document.getElementById(
                    "textError"
                );

            error.style.display = "none";
            status.style.display = "block";

            const formData =
                new FormData();

            formData.append(
                "file",
                currentTextFile
            );

            formData.append(
                "name",
                currentTextName
            );

            formData.append(
                "size",
                textSize.value
            );

            formData.append(
                "height",
                textHeight.value
            );

            try {
                const response =
                    await fetch(
                        "/create-text",
                        {
                            method: "POST",
                            body: formData
                        }
                    );

                if (!response.ok) {
                    const data =
                        await response.json();

                    throw new Error(
                        data.error ||
                        "Не удалось создать STL"
                    );
                }

                const blob =
                    await response.blob();

                const url =
                    URL.createObjectURL(
                        blob
                    );

                const a =
                    document.createElement(
                        "a"
                    );

                a.href = url;

                a.download =
                    currentTextName +
                    ".stl";

                document.body.appendChild(
                    a
                );

                a.click();
                a.remove();

                URL.revokeObjectURL(
                    url
                );
            }

            catch (e) {
                error.textContent =
                    e.message;

                error.style.display =
                    "block";
            }

            status.style.display =
                "none";
        }
    );


    document.getElementById(
        "textAnotherButton"
    ).addEventListener(
        "click",
        function () {

            textFile.value = "";
            currentTextFile = "";
            currentTextName = "";

            document.getElementById(
                "textPreviewBox"
            ).style.display =
                "none";

            document.getElementById(
                "textSettings"
            ).style.display =
                "none";

            document.getElementById(
                "textCreateButton"
            ).style.display =
                "none";

            document.getElementById(
                "textAnotherButton"
            ).style.display =
                "none";

            document.getElementById(
                "textError"
            ).style.display =
                "none";

            const label =
                document.getElementById(
                    "textUploadLabel"
                );

            label.style.display =
                "block";

            label.textContent =
                "Загрузить букву или цифру";
        }
    );
</script>

</body>
</html>
"""


@app.get(
    "/",
    response_class=HTMLResponse,
)
def home():
    return PAGE


async def save_upload(file):
    original_name = os.path.basename(
        file.filename
    )

    name, extension = os.path.splitext(
        original_name
    )

    unique_name = (
        uuid.uuid4().hex
        + extension.lower()
    )

    path = os.path.join(
        "input",
        unique_name
    )

    with open(
        path,
        "wb"
    ) as f:
        f.write(
            await file.read()
        )

    return (
        unique_name,
        name,
        path,
    )


@app.post("/prepare-image")
async def prepare_image(
    file: UploadFile = File(...),
):
    try:
        stored_file, original_name, input_path = (
            await save_upload(file)
        )

        subprocess.run(
            [
                sys.executable,
                "main.py",
                input_path,
                "100",
                "10",
            ],
            check=True,
        )

        return {
            "file": stored_file,
            "name": original_name,
        }

    except subprocess.CalledProcessError:
        return JSONResponse(
            {
                "error":
                "Не удалось обработать изображение"
            },
            status_code=500,
        )


@app.post("/create-image")
async def create_image(
    file: str = Form(...),
    name: str = Form(...),
    size: float = Form(...),
    height: float = Form(...),
):
    input_path = os.path.join(
        "input",
        os.path.basename(file),
    )

    if not os.path.exists(input_path):
        return JSONResponse(
            {
                "error":
                "Исходное изображение не найдено"
            },
            status_code=404,
        )

    try:
        subprocess.run(
            [
                sys.executable,
                "main.py",
                input_path,
                str(size),
                str(height),
            ],
            check=True,
        )

    except subprocess.CalledProcessError:
        return JSONResponse(
            {
                "error":
                "Не удалось создать STL"
            },
            status_code=500,
        )

    generated_name = (
        os.path.splitext(file)[0]
        + ".stl"
    )

    output_path = os.path.join(
        "output",
        generated_name,
    )

    if not os.path.exists(output_path):
        return JSONResponse(
            {
                "error":
                "STL-файл не найден после создания"
            },
            status_code=500,
        )

    return FileResponse(
        output_path,
        filename=name + ".stl",
    )


@app.post("/prepare-text")
async def prepare_text(
    file: UploadFile = File(...),
):
    try:
        stored_file, original_name, input_path = (
            await save_upload(file)
        )

        subprocess.run(
            [
                sys.executable,
                "main_text.py",
                input_path,
                "100",
                "10",
            ],
            check=True,
        )

        return {
            "file": stored_file,
            "name": original_name,
        }

    except subprocess.CalledProcessError:
        return JSONResponse(
            {
                "error":
                "Не удалось обработать букву или цифру"
            },
            status_code=500,
        )


@app.post("/create-text")
async def create_text(
    file: str = Form(...),
    name: str = Form(...),
    size: float = Form(...),
    height: float = Form(...),
):
    input_path = os.path.join(
        "input",
        os.path.basename(file),
    )

    if not os.path.exists(input_path):
        return JSONResponse(
            {
                "error":
                "Исходное изображение не найдено"
            },
            status_code=404,
        )

    try:
        subprocess.run(
            [
                sys.executable,
                "main_text.py",
                input_path,
                str(size),
                str(height),
            ],
            check=True,
        )

    except subprocess.CalledProcessError:
        return JSONResponse(
            {
                "error":
                "Не удалось создать STL"
            },
            status_code=500,
        )

    generated_name = (
        os.path.splitext(file)[0]
        + ".stl"
    )

    output_path = os.path.join(
        "output",
        generated_name,
    )

    if not os.path.exists(output_path):
        return JSONResponse(
            {
                "error":
                "STL-файл не найден после создания"
            },
            status_code=500,
        )

    return FileResponse(
        output_path,
        filename=name + ".stl",
    )


@app.get("/preview-image")
def preview_image():
    path = "output/vector_outline.png"

    if not os.path.exists(path):
        return JSONResponse(
            {
                "error":
                "Предпросмотр ещё не создан"
            },
            status_code=404,
        )

    return FileResponse(path)


@app.get("/preview-text")
def preview_text():
    path = "output/text_outline.png"

    if not os.path.exists(path):
        return JSONResponse(
            {
                "error":
                "Предпросмотр ещё не создан"
            },
            status_code=404,
        )

    return FileResponse(path)
