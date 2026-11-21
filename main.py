import os
import asyncio
import xml.etree.ElementTree as ET

import httpx
import uvicorn

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


# =========================
# CONFIGURATION
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com")
PORT = int(os.getenv("PORT", "8000"))

app = FastAPI(
    title="Market Analytics API",
    docs_url=None,
    redoc_url=None
)

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


# =========================
# RSI CALCULATION
# =========================

def calculate_rsi(closes, period=14):

    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(closes)):
        difference = closes[i] - closes[i - 1]

        gains.append(max(difference, 0))
        losses.append(max(-difference, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss

    return round(100 - (100 / (1 + rs)), 1)


# =========================
# SERVER HEALTH
# =========================

@app.get("/ping")
async def ping():

    return {
        "status": "ok",
        "service": "Market Analytics"
    }


# =========================
# WEB APP
# =========================

@app.get("/", response_class=HTMLResponse)
async def serve_webapp():

    try:
        with open("index.html", "r", encoding="utf-8") as file:
            return file.read()

    except FileNotFoundError:
        return HTMLResponse(
            "<h1>index.html not found</h1>",
            status_code=404
        )


# =========================
# MARKET DATA
# =========================

@app.get("/api/market")
async def get_market_data():

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:

            # BYBIT BTC/USDT

            bybit_response = await client.get(
                "https://api.bybit.com/v5/market/kline",
                params={
                    "category": "spot",
                    "symbol": "BTCUSDT",
                    "interval": "60",
                    "limit": "50"
                }
            )

            bybit_response.raise_for_status()

            bybit_data = bybit_response.json()

            if bybit_data.get("retCode") != 0:
                raise ValueError("Bybit API returned an error")

            klines = bybit_data["result"]["list"]

            if not klines:
                raise ValueError("No market candles available")

            # BYBIT returns newest candles first
            klines.reverse()

            candles = []
            closes = []

            for k in klines:

                candle = {
                    "time": int(k[0]) // 1000,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4])
                }

                candles.append(candle)
                closes.append(candle["close"])

            current_rsi = calculate_rsi(closes)

            # MARKET SIGNAL

            if current_rsi > 70:
                signal = "Перекуплен — повышенный риск коррекции"

            elif current_rsi < 30:
                signal = "Перепродан — возможен отскок"

            else:
                signal = "Нейтральный рынок"

            # CENTRAL BANK OF RUSSIA

            usd_rate = None

            try:
                cbr_response = await client.get(
                    "https://www.cbr.ru/scripts/XML_daily.asp"
                )

                cbr_response.raise_for_status()

                root = ET.fromstring(cbr_response.content)

                for currency in root.findall("Valute"):

                    code = currency.findtext("CharCode")

                    if code == "USD":
                        value = currency.findtext("Value")

                        if value:
                            usd_rate = float(
                                value.replace(",", ".")
                            )

                        break

            except (
                httpx.HTTPError,
                ET.ParseError,
                ValueError
            ):
                usd_rate = None

            return {
                "status": "ok",
                "btc_price": closes[-1],
                "usd_cbr": usd_rate,
                "rsi": current_rsi,
                "signal": signal,
                "candles": candles
            }

    except (
        httpx.HTTPError,
        KeyError,
        ValueError,
        TypeError
    ) as error:

        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": str(error)
            }
        )


# =========================
# TELEGRAM BOT
# =========================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Открыть аналитику рынка",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ]
    )

    await message.answer(
        "Добро пожаловать!\n\n"
        "Откройте приложение для просмотра "
        "графиков и рыночных индикаторов.",
        reply_markup=keyboard
    )


# =========================
# APPLICATION START
# =========================

async def main():

async def main():

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT
    )

    server = uvicorn.Server(config)

    if not bot:
        print("BOT_TOKEN отсутствует. Запускаем только API.")
        await server.serve()
        return

    try:
        await bot.get_me()
    except Exception as error:
        print(
            "Telegram bot authorization failed:",
            type(error).__name__
        )
        await bot.session.close()
        await server.serve()
        return

    try:
        await asyncio.gather(
            server.serve(),
            dp.start_polling(bot)
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT
    )

    server = uvicorn.Server(config)

    if bot:

        await asyncio.gather(
            server.serve(),
            dp.start_polling(bot)
        )

    else:

        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

