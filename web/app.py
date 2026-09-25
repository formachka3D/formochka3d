from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import os
import subprocess
import sys
import uuid
import asyncio
import shutil


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
                Загрузите фотографию, рисунок или готовый силуэт.<br><span style="font-size:13px;color:#99877e">JPG · PNG · WEBP</span>
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

            <button class="create-button" id="imageConfirmContour" type="button" style="display:none">Подтвердить контур</button>

            <section id="imageModelStage" style="display:none; margin-top:22px; text-align:center"><h3>Ваша формочка в 3D</h3><p>Вращайте модель мышью или пальцем.</p><div id="imageModelViewer" style="height:320px; border:1px solid #eee5df; border-radius:18px; overflow:hidden"></div><p>Настройте размер и высоту под моделью.</p>            <div
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

<p id="imageModelMessage" role="status">Подготавливаем модель...</p><button type="button" disabled style="padding:16px; width:100%; border-radius:14px; opacity:.65">Заказать готовую формочку — скоро</button></section>
            <button
                class="create-button"
                id="imageCreateButton"
            >
                Скачать STL
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

            <div class="upload-area" id="textIntroArea">
                <img class="example-image" src="/static/example_text.png" alt="Буква и цифра, формочка и готовый пряник">
                <button class="main-button" id="textStartButton" type="button">Выбрать букву или цифру</button>
            </div>
            <div class="upload-area" id="textSelectionArea" style="display:none">
                <p style="font-weight:700;margin:0 0 12px">Выберите букву или цифру</p>
                <div id="textSymbolGrid" role="group" aria-label="Алфавит и цифры" style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;margin-bottom:18px"></div>
                <label for="textFont" style="display:block;font-weight:700;margin-bottom:8px">Шрифт</label>
                <select id="textFont" style="width:100%;padding:12px;border:1px solid #e4d4ca;border-radius:12px;font-size:16px">
                    <option value="Arial">Обычный — Arial</option>
                    <option value="Arial Black">Жирный — Arial Black</option>
                    <option value="Georgia">Классический — Georgia</option>
                    <option value="Trebuchet MS">Округлый — Trebuchet</option>
                    <option value="Comic Sans MS">Весёлый — Comic Sans</option>
                </select>
                <div id="textGlyphPreview" aria-live="polite" style="height:135px;display:flex;align-items:center;justify-content:center;font-size:100px;overflow:hidden">А</div>
                <button class="main-button" id="textUploadLabel" type="button">Создать контур</button>
            </div>
            <input id="textFile" type="file" accept="image/png" style="display:none">
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

            <button class="create-button" id="textConfirmContour" type="button" style="display:none">Подтвердить контур</button>
            <section id="textModelStage" style="display:none; margin-top:22px; text-align:center"><h3>Ваша формочка в 3D</h3><p>Вращайте модель мышью или пальцем.</p><div id="textModelViewer" style="height:320px; border:1px solid #eee5df; border-radius:18px; overflow:hidden"></div><p>Настройте размер и высоту под моделью.</p>            <div
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

<p id="textModelMessage" role="status">Подготавливаем модель...</p><button type="button" disabled style="padding:16px; width:100%; border-radius:14px; opacity:.65">Заказать готовую формочку — скоро</button></section>
            <button class="create-button" id="textCreateButton" type="button" disabled>Скачать STL</button>
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
                    "/preview-image?file=" + encodeURIComponent(currentImageFile) + "&t=" + Date.now();

                document.getElementById(
                    "imagePreviewBox"
                ).style.display =
                    "block";

                document.getElementById("imageConfirmContour").style.display = "block";
                document.getElementById("imageSettings").style.display = "none";
                document.getElementById("imageModelStage").style.display = "none";
                window.dispatchEvent(new Event("formochka:clear"));
                document.getElementById("imageCreateButton").style.display = "none";

                document.getElementById(
                    "imageAnotherButton"
                ).style.display =
                    "block";

                label.style.display =
                    "none";
                document.getElementById("textSelectionArea").style.display="none";
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


    document.getElementById("imageCreateButton").addEventListener("click",()=>{
        const blob=window.formochkaSTL;
        if(!blob)return;
        const url=URL.createObjectURL(blob),link=document.createElement("a");
        link.href=url;link.download=currentImageName+".stl";
        document.body.appendChild(link);link.click();link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
    });

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

            document.getElementById("imageConfirmContour").style.display = "none";
            document.getElementById("imageSettings").style.display = "none";
            document.getElementById("imageModelStage").style.display = "none";
            window.dispatchEvent(new Event("formochka:clear"));

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


    document.getElementById("imageConfirmContour").addEventListener("click", function () {
        this.style.display = "none";
        document.getElementById("imagePreviewBox").style.display = "none";
        document.getElementById("imageSettings").style.display = "block";
        document.getElementById("imageModelStage").style.display = "block";
        document.getElementById("imageCreateButton").style.display = "block";
        window.dispatchEvent(new Event("formochka:build"));
    });
    for (const slider of [imageSize,imageHeight]) slider.addEventListener("input",()=>{
        if (document.getElementById("imageModelStage").style.display === "block") window.dispatchEvent(new Event("formochka:build"));
    });

    document.getElementById("textStartButton").addEventListener("click",()=>{
        document.getElementById("textIntroArea").style.display="none";
        document.getElementById("textSelectionArea").style.display="block";
        document.getElementById("textSelectionArea").scrollIntoView({behavior:"smooth",block:"start"});
    });
    // Letter/number selector: generate a clean black silhouette locally.
    const textGrid=document.getElementById("textSymbolGrid");
    const textFont=document.getElementById("textFont");
    const textGlyphPreview=document.getElementById("textGlyphPreview");
    let chosenSymbol="А";
    const symbols=Array.from("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789");
    function updateGlyph(){
        textGlyphPreview.textContent=chosenSymbol;
        textGlyphPreview.style.fontFamily='"'+textFont.value+'",sans-serif';
        for(const button of textGrid.children)button.setAttribute("aria-pressed",String(button.textContent===chosenSymbol));
    }
    for(const symbol of symbols){
        const button=document.createElement("button");
        button.type="button";button.textContent=symbol;
        button.setAttribute("aria-label","Выбрать "+symbol);
        button.style.cssText="min-width:0;height:40px;border:1px solid #e4d4ca;border-radius:9px;background:white;color:#332b28;font-weight:bold;cursor:pointer";
        button.addEventListener("click",()=>{
            chosenSymbol=symbol;updateGlyph();
            for(const item of textGrid.children){const active=item.textContent===symbol;item.style.background=active?"#e8844e":"white";item.style.color=active?"white":"#332b28";}
        });
        textGrid.append(button);
    }
    textGrid.firstElementChild.click();
    textFont.addEventListener("change",updateGlyph);
    document.getElementById("textUploadLabel").addEventListener("click",async()=>{
        const button=document.getElementById("textUploadLabel");
        button.disabled=true;button.textContent="Подготавливаем символ...";
        try{
            const font=textFont.value,weight=font==="Arial Black"?"900":"normal";
            await document.fonts.load(weight+' 900px "'+font+'"',chosenSymbol);
            const canvas=document.createElement("canvas");canvas.width=canvas.height=1600;
            const ctx=canvas.getContext("2d");
            ctx.fillStyle="white";ctx.fillRect(0,0,1600,1600);
            ctx.fillStyle="black";ctx.textAlign="center";ctx.textBaseline="middle";
            ctx.font=weight+' 1050px "'+font+'",sans-serif';
            ctx.fillText(chosenSymbol,800,800);
            const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));
            if(!blob)throw Error("Не удалось нарисовать символ");
            const file=new File([blob],chosenSymbol+"_"+font.replaceAll(" ","_")+".png",{type:"image/png"});
            const transfer=new DataTransfer();transfer.items.add(file);
            document.getElementById("textFile").files=transfer.files;
            document.getElementById("textFile").dispatchEvent(new Event("change"));
        }catch(error){
            const label=document.getElementById("textError");
            label.textContent=error.message;label.style.display="block";
        }finally{button.disabled=false;button.textContent="Создать контур";}
    });
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
                    "/preview-text?file=" + encodeURIComponent(currentTextFile) + "&t=" + Date.now();

                document.getElementById(
                    "textPreviewBox"
                ).style.display =
                    "block";

                document.getElementById("textConfirmContour").style.display = "block";
                document.getElementById("textModelStage").style.display = "none";
                window.dispatchEvent(new Event("formochka:text-clear"));

                document.getElementById(
                    "textAnotherButton"
                ).style.display =
                    "block";

                label.style.display =
                    "none";
                document.getElementById("textSelectionArea").style.display="none";
            }

            catch (e) {
                label.style.display =
                    "block";

                label.textContent =
                    "Создать контур";

                error.textContent =
                    e.message;

                error.style.display =
                    "block";
            }
        }
    );


    document.getElementById("textConfirmContour").addEventListener("click", function () {
        this.style.display = "none";
        document.getElementById("textPreviewBox").style.display = "none";
        document.getElementById("textModelStage").style.display = "block";
        document.getElementById("textSettings").style.display = "block";
        document.getElementById("textCreateButton").style.display = "block";
        window.dispatchEvent(new Event("formochka:text-build"));
    });
    for (const slider of [textSize,textHeight]) slider.addEventListener("input",()=>{
        if (document.getElementById("textModelStage").style.display === "block") window.dispatchEvent(new Event("formochka:text-build"));
    });
    document.getElementById("textCreateButton").addEventListener("click",()=>{
        const blob=window.formochkaTextSTL;if(!blob)return;
        const url=URL.createObjectURL(blob),link=document.createElement("a");
        link.href=url;link.download=currentTextName+".stl";document.body.appendChild(link);link.click();link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
    });

    document.getElementById(
        "textAnotherButton"
    ).addEventListener(
        "click",
        function () {

            textFile.value = "";
            currentTextFile = "";
            currentTextName = "";
            document.getElementById("textConfirmContour").style.display = "none";
            document.getElementById("textModelStage").style.display = "none";
            window.dispatchEvent(new Event("formochka:text-clear"));

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
            document.getElementById("textSelectionArea").style.display="none";
            document.getElementById("textIntroArea").style.display="block";

            label.textContent =
                "Создать контур";
            document.getElementById("textIntroArea").scrollIntoView({behavior: "smooth", block: "center"});
        }
    );
</script>

<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.1/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import {STLLoader} from "three/addons/loaders/STLLoader.js";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";
const holder=document.getElementById("imageModelViewer"),message=document.getElementById("imageModelMessage"),button=document.getElementById("imageCreateButton");
let version=0,timer,controller,view;
window.formochkaSTL=null;
function clear(){if(view){view.stop();view.controls.dispose();view.geometry.dispose();view.material.dispose();view.renderer.dispose();view.renderer.domElement.remove();view=null;}}
window.addEventListener("formochka:clear",()=>{version++;clearTimeout(timer);controller?.abort();clear();window.formochkaSTL=null;button.disabled=true;});
window.addEventListener("formochka:build",()=>{version++;clearTimeout(timer);controller?.abort();window.formochkaSTL=null;button.disabled=true;message.textContent="Создаём 3D-модель...";const v=version;timer=setTimeout(()=>build(v),450);});
async function build(v){
 controller=new AbortController();
 const form=new FormData();form.append("file",currentImageFile);form.append("name",currentImageName);form.append("size",imageSize.value);form.append("height",imageHeight.value);
 try{
 const response=await fetch("/create-image",{method:"POST",body:form,signal:controller.signal});
 if(!response.ok){const e=await response.json().catch(()=>({}));throw Error(e.error||"Ошибка генерации");}
 const blob=await response.blob();if(v!==version)return;
 const geometry=new STLLoader().parse(await blob.arrayBuffer());if(v!==version){geometry.dispose();return;}
 clear();geometry.computeVertexNormals();geometry.computeBoundingBox();geometry.center();
 const scene=new THREE.Scene();scene.background=new THREE.Color(0xfff7f2);
 const material=new THREE.MeshStandardMaterial({color:0xd58d6d,side:THREE.DoubleSide,roughness:.7});
 const mesh=new THREE.Mesh(geometry,material);mesh.rotation.x=-Math.PI/2;scene.add(mesh);
 scene.add(new THREE.HemisphereLight(0xffffff,0x967967,2));
 const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(100,150,100);scene.add(light);
 const width=holder.clientWidth||320,renderer=new THREE.WebGLRenderer({antialias:true});renderer.setSize(width,320);holder.replaceChildren(renderer.domElement);
 const camera=new THREE.PerspectiveCamera(45,width/320,.1,3000),span=geometry.boundingBox.getSize(new THREE.Vector3()).length();
 camera.position.set(span*.8,span*.85,span*.9);camera.lookAt(0,0,0);
 const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
 let running=true;function frame(){if(!running)return;controls.update();renderer.render(scene,camera);requestAnimationFrame(frame);}
 view={stop:()=>{running=false;},controls,geometry,material,renderer};frame();
 window.formochkaSTL=blob;button.disabled=false;message.textContent="Модель готова. Её можно вращать и скачать.";
 }catch(e){if(v===version&&e.name!=="AbortError")message.textContent=e.message;}
}
{
const holder=document.getElementById("textModelViewer"),message=document.getElementById("textModelMessage"),button=document.getElementById("textCreateButton");
let version=0,timer,controller,view;
window.formochkaTextSTL=null;
function clear(){if(view){view.stop();view.controls.dispose();view.geometry.dispose();view.material.dispose();view.renderer.dispose();view.renderer.domElement.remove();view=null;}}
window.addEventListener("formochka:text-clear",()=>{version++;clearTimeout(timer);controller?.abort();clear();window.formochkaTextSTL=null;button.disabled=true;});
window.addEventListener("formochka:text-build",()=>{version++;clearTimeout(timer);controller?.abort();window.formochkaTextSTL=null;button.disabled=true;message.textContent="Создаём 3D-модель...";const v=version;timer=setTimeout(()=>build(v),450);});
async function build(v){
 controller=new AbortController();
 const form=new FormData();form.append("file",currentTextFile);form.append("name",currentTextName);form.append("size",textSize.value);form.append("height",textHeight.value);
 try{
 const response=await fetch("/create-text",{method:"POST",body:form,signal:controller.signal});
 if(!response.ok){const e=await response.json().catch(()=>({}));throw Error(e.error||"Ошибка генерации");}
 const blob=await response.blob();if(v!==version)return;
 const geometry=new STLLoader().parse(await blob.arrayBuffer());if(v!==version){geometry.dispose();return;}
 clear();geometry.computeVertexNormals();geometry.computeBoundingBox();geometry.center();
 const scene=new THREE.Scene();scene.background=new THREE.Color(0xfff7f2);
 const material=new THREE.MeshStandardMaterial({color:0xd58d6d,side:THREE.DoubleSide,roughness:.7});
 const mesh=new THREE.Mesh(geometry,material);mesh.rotation.x=-Math.PI/2;scene.add(mesh);
 scene.add(new THREE.HemisphereLight(0xffffff,0x967967,2));
 const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(100,150,100);scene.add(light);
 const width=holder.clientWidth||320,renderer=new THREE.WebGLRenderer({antialias:true});renderer.setSize(width,320);holder.replaceChildren(renderer.domElement);
 const camera=new THREE.PerspectiveCamera(45,width/320,.1,3000),span=geometry.boundingBox.getSize(new THREE.Vector3()).length();
 camera.position.set(span*.8,span*.85,span*.9);camera.lookAt(0,0,0);
 const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
 let running=true;function frame(){if(!running)return;controls.update();renderer.render(scene,camera);requestAnimationFrame(frame);}
 view={stop:()=>{running=false;},controls,geometry,material,renderer};frame();
 window.formochkaTextSTL=blob;button.disabled=false;message.textContent="Модель готова. Её можно вращать и скачать.";
 }catch(e){if(v===version&&e.name!=="AbortError")message.textContent=e.message;}
}

}
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
    original_name = os.path.basename(file.filename or "")
    name, extension = os.path.splitext(original_name)
    extension = extension.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Поддерживаются JPG, PNG и WEBP")

    unique_name = uuid.uuid4().hex + extension
    path = os.path.join("input", unique_name)
    max_bytes = 10 * 1024 * 1024
    total = 0
    try:
        with open(path, "wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Изображение больше 10 МБ")
                destination.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Пустое изображение")
    except BaseException:
        if os.path.exists(path):
            os.remove(path)
        raise
    return unique_name, name or "formochka", path


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


async def _create_stl(file: str, name: str, size: float, height: float, script: str):
    if not _valid_upload_name(file):
        return JSONResponse({"error": "Неверный файл"}, status_code=400)
    if not (40 <= size <= 200 and 5 <= height <= 30):
        return JSONResponse({"error": "Недопустимые размеры"}, status_code=400)
    source = os.path.join("input", file)
    if not os.path.isfile(source):
        return JSONResponse({"error": "Исходное изображение не найдено"}, status_code=404)

    # Each preview generation uses its own input/output basename.
    # Overlapping slider requests must never overwrite each other's STL.
    run_name = uuid.uuid4().hex
    extension = os.path.splitext(file)[1]
    run_input = os.path.join("input", run_name + extension)
    output_path = os.path.join("output", run_name + ".stl")
    preview_path = os.path.join("output", run_name + "_outline.png")
    shutil.copyfile(source, run_input)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, script, run_input, str(size), str(height),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0 or not os.path.isfile(output_path):
            return JSONResponse({"error": "Не удалось создать STL"}, status_code=500)
        # Read before cleanup: FileResponse streams only after the endpoint returns.
        with open(output_path, "rb") as model:
            payload = model.read()
        from fastapi.responses import Response
        safe_name = os.path.basename(name).replace('"', '') or "formochka"
        from urllib.parse import quote
        return Response(
            content=payload,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(safe_name + ".stl")},
        )
    finally:
        for path in (run_input, output_path, preview_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


@app.post("/create-image")
async def create_image(
    file: str = Form(...),
    name: str = Form(...),
    size: float = Form(...),
    height: float = Form(...),
):
    return await _create_stl(file, name, size, height, "main.py")


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
    return await _create_stl(file, name, size, height, "main_text.py")


def _valid_upload_name(value: str) -> bool:
    stem, ext = os.path.splitext(value)
    return len(stem) == 32 and all(ch in "0123456789abcdef" for ch in stem) and ext.lower() in {".png", ".jpg", ".jpeg", ".webp"}


@app.get("/preview-image")
def preview_image(file: str):
    if not _valid_upload_name(file):
        return JSONResponse({"error": "Неверный файл"}, status_code=400)
    path = os.path.join("output", os.path.splitext(file)[0] + "_outline.png")

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
def preview_text(file: str):
    if not _valid_upload_name(file):
        return JSONResponse({"error": "Неверный файл"}, status_code=400)
    path = os.path.join("output", os.path.splitext(file)[0] + "_outline.png")

    if not os.path.exists(path):
        return JSONResponse(
            {
                "error":
                "Предпросмотр ещё не создан"
            },
            status_code=404,
        )

    return FileResponse(path)
