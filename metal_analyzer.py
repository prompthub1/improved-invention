import pandas as pd
import numpy as np
import yfinance as yf
import requests
import time
from datetime import datetime, timedelta
import logging
from typing import Dict, Tuple, List
import talib
import os
import sys

# تنظیمات پیشرفته لاگ‌گیری
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class MetalMarketAnalyzer:
    def __init__(self):
        # دریافت توکن و آیدی از environment variables
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
        
        # اگر channel_id با @ شروع شود، باید به عدد تبدیل شود
        if self.channel_id and self.channel_id.startswith('@'):
            self.channel_id = self.convert_to_chat_id(self.channel_id)
        
        logging.info(f"TELEGRAM_BOT_TOKEN: {'***' + self.bot_token[-4:] if self.bot_token else 'NOT SET'}")
        logging.info(f"TELEGRAM_CHANNEL_ID: {self.channel_id}")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN تنظیم نشده است")
        if not self.channel_id:
            raise ValueError("TELEGRAM_CHANNEL_ID تنظیم نشده است")
            
        self.metals = {
            'gold': 'GC=F',
            'silver': 'SI=F'
        }
    
    def convert_to_chat_id(self, channel_username: str) -> str:
        """تبدیل آیدی کانال به Chat ID عددی"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data['ok'] and data['result']:
                    for update in data['result']:
                        if 'channel_post' in update:
                            chat = update['channel_post']['chat']
                            if chat.get('username') == channel_username[1:]:  # حذف @
                                chat_id = chat['id']
                                logging.info(f"کانال {channel_username} با Chat ID {chat_id} پیدا شد")
                                return str(chat_id)
            
            logging.warning(f"نمی‌توان Chat ID کانال {channel_username} را پیدا کرد")
            return channel_username  # بازگشت به حالت قبلی اگر پیدا نشد
            
        except Exception as e:
            logging.error(f"خطا در تبدیل آیدی کانال: {e}")
            return channel_username
    
    def is_holiday(self, date: datetime) -> bool:
        """بررسی تعطیلی بازار - برای فارکس تعطیلی خاصی نداریم"""
        # بازار فارکس 24/5 باز است و فقط آخر هفته‌ها بسته است
        # این تابع را خالی می‌گذاریم چون فارکس تعطیلی رسمی ندارد
        return False
    
    def is_weekend(self, date: datetime) -> bool:
        """بررسی آخر هفته - فارکس فقط جمعه و شنبه بسته است"""
        # بازار فارکس از یکشنبه تا جمعه باز است
        # جمعه و شنبه بسته است (بر اساس بازارهای بین‌المللی)
        return date.weekday() >= 5  # 5=شنبه, 6=یکشنبه
    
    def should_analyze(self) -> bool:
        """بررسی زمان تحلیل - برای فارکس محدودیت زمانی نداریم"""
        now = datetime.now()
        
        # فقط آخر هفته تحلیل نکن
        if self.is_weekend(now):
            logging.info("امروز بازار فارکس تعطیل است (آخر هفته)")
            return False
            
        # برای فارکس هیچ محدودیت ساعتی نداریم
        # بازار فارکس 24 ساعته از یکشنبه تا جمعه باز است
        return True
    
    def get_metal_data(self, symbol: str, period: str = '1mo') -> pd.DataFrame:
        """دریافت داده‌های فلز"""
        try:
            logging.info(f"دریافت داده برای {symbol} با دوره {period}")
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval='15m')
            logging.info(f"تعداد داده‌های دریافت شده: {len(data)}")
            return data
        except Exception as e:
            logging.error(f"خطا در دریافت داده برای {symbol}: {e}")
            return None
    
    def calculate_indicators(self, data: pd.DataFrame) -> Dict:
        """محاسبه اندیکاتورهای تکنیکال"""
        if len(data) < 50:
            logging.warning("داده کافی برای محاسبه اندیکاتورها موجود نیست")
            return {}
        
        try:
            close_prices = data['Close'].values
            high_prices = data['High'].values
            low_prices = data['Low'].values
            
            # محاسبه اندیکاتورها
            indicators = {}
            
            # RSI
            rsi = talib.RSI(close_prices, timeperiod=14)
            indicators['rsi'] = rsi[-1] if len(rsi) > 0 else 50
            
            # Moving Averages
            sma_20 = talib.SMA(close_prices, timeperiod=20)
            sma_50 = talib.SMA(close_prices, timeperiod=50)
            indicators['sma_20'] = sma_20[-1] if len(sma_20) > 0 else 0
            indicators['sma_50'] = sma_50[-1] if len(sma_50) > 0 else 0
            
            # MACD
            macd, macd_signal, macd_hist = talib.MACD(close_prices)
            indicators['macd'] = macd[-1] if len(macd) > 0 else 0
            indicators['macd_signal'] = macd_signal[-1] if len(macd_signal) > 0 else 0
            indicators['macd_hist'] = macd_hist[-1] if len(macd_hist) > 0 else 0
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = talib.BBANDS(close_prices, timeperiod=20, nbdevup=2, nbdevdn=2)
            if len(bb_upper) > 0 and len(bb_lower) > 0:
                indicators['bb_upper'] = bb_upper[-1]
                indicators['bb_middle'] = bb_middle[-1]
                indicators['bb_lower'] = bb_lower[-1]
                indicators['bb_position'] = (close_prices[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1])
            else:
                indicators['bb_position'] = 0.5
            
            return indicators
        except Exception as e:
            logging.error(f"خطا در محاسبه اندیکاتورها: {e}")
            return {}
    
    def analyze_trend(self, data: pd.DataFrame) -> Dict:
        """تحلیل روند و سقف/کف‌ها"""
        if len(data) < 20:
            return {}
        
        try:
            # تحلیل 4 ساعت گذشته (16 کندل 15 دقیقه‌ای)
            recent_data = data.tail(16)
            highs = recent_data['High'].values
            lows = recent_data['Low'].values
            
            # یافتن سقف و کف‌ها
            higher_highs = 0
            lower_highs = 0
            higher_lows = 0
            lower_lows = 0
            
            for i in range(1, len(highs)):
                if highs[i] > highs[i-1]:
                    higher_highs += 1
                elif highs[i] < highs[i-1]:
                    lower_highs += 1
                    
                if lows[i] > lows[i-1]:
                    higher_lows += 1
                elif lows[i] < lows[i-1]:
                    lower_lows += 1
            
            trend_analysis = {
                'higher_highs': higher_highs,
                'lower_highs': lower_highs,
                'higher_lows': higher_lows,
                'lower_lows': lower_lows,
                'trend_strength': (higher_highs + higher_lows - lower_highs - lower_lows) / 30
            }
            
            return trend_analysis
        except Exception as e:
            logging.error(f"خطا در تحلیل روند: {e}")
            return {}
    
    def get_signal_strength(self, indicators: Dict, trend_analysis: Dict) -> Tuple[str, float, str]:
        """محاسبه قدرت سیگنال"""
        try:
            confirmation_count = 0
            total_indicators = 5
            
            current_price = indicators.get('current_price', 0)
            sma_20 = indicators.get('sma_20', 0)
            sma_50 = indicators.get('sma_50', 0)
            rsi = indicators.get('rsi', 50)
            macd_hist = indicators.get('macd_hist', 0)
            bb_position = indicators.get('bb_position', 0.5)
            trend_strength = trend_analysis.get('trend_strength', 0)
            
            # تحلیل RSI
            if rsi < 30:
                rsi_signal = "خرید"
                confirmation_count += 1
            elif rsi > 70:
                rsi_signal = "فروش"
                confirmation_count += 1
            else:
                rsi_signal = "خنثی"
            
            # تحلیل موینگ اوریج
            if sma_20 > sma_50 and current_price > sma_20:
                ma_signal = "خرید"
                confirmation_count += 1
            elif sma_20 < sma_50 and current_price < sma_20:
                ma_signal = "فروش"
                confirmation_count += 1
            else:
                ma_signal = "خنثی"
            
            # تحلیل MACD
            if macd_hist > 0:
                macd_signal = "خرید"
                confirmation_count += 1
            elif macd_hist < 0:
                macd_signal = "فروش"
                confirmation_count += 1
            else:
                macd_signal = "خنثی"
            
            # تحلیل بولینگر باند
            if bb_position < 0.2:
                bb_signal = "خرید"
                confirmation_count += 1
            elif bb_position > 0.8:
                bb_signal = "فروش"
                confirmation_count += 1
            else:
                bb_signal = "خنثی"
            
            # تحلیل روند
            if trend_strength > 0.1:
                trend_signal = "خرید"
                confirmation_count += 1
            elif trend_strength < -0.1:
                trend_signal = "فروش"
                confirmation_count += 1
            else:
                trend_signal = "خنثی"
            
            # محاسبه درصد اطمینان
            if confirmation_count == total_indicators:
                confidence = 80
            elif confirmation_count == total_indicators - 1:
                confidence = 70
            elif confirmation_count == total_indicators - 2:
                confidence = 60
            else:
                confidence = 50
            
            # تعیین جهت کلی بازار
            buy_signals = sum([1 for signal in [rsi_signal, ma_signal, macd_signal, bb_signal, trend_signal] if signal == "خرید"])
            sell_signals = sum([1 for signal in [rsi_signal, ma_signal, macd_signal, bb_signal, trend_signal] if signal == "فروش"])
            
            if buy_signals > sell_signals:
                market_direction = "صعودی"
                action = "خرید"
            elif sell_signals > buy_signals:
                market_direction = "نزولی"
                action = "فروش"
            else:
                market_direction = "رنج"
                action = "انتظار"
            
            signals_detail = {
                'RSI': rsi_signal,
                'MA': ma_signal,
                'MACD': macd_signal,
                'Bollinger': bb_signal,
                'Trend': trend_signal
            }
            
            return market_direction, confidence, action, signals_detail
        except Exception as e:
            logging.error(f"خطا در محاسبه قدرت سیگنال: {e}")
            return "نامشخص", 0, "نامشخص", {}
    
    def get_daily_summary(self) -> str:
        """گزارش روزانه قیمت فلزات"""
        try:
            message = "📊 گزارش روزانه فلزات 📊\n\n"
            message += f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            
            for metal_name, symbol in self.metals.items():
                data_30d = self.get_metal_data(symbol, '1mo')
                if data_30d is not None and len(data_30d) > 0:
                    # استفاده از iloc به جای [] برای جلوگیری از هشدار
                    current_price = data_30d['Close'].iloc[-1] if len(data_30d) > 0 else 0
                    price_30d_ago = data_30d['Close'].iloc[0] if len(data_30d) > 0 else 0
                    
                    if price_30d_ago > 0:
                        change_percent = ((current_price - price_30d_ago) / price_30d_ago) * 100
                    else:
                        change_percent = 0
                    
                    change_emoji = "📈" if change_percent > 0 else "📉"
                    
                    message += f"{metal_name.upper()}:\n"
                    message += f"💰 قیمت فعلی: ${current_price:.2f}\n"
                    message += f"{change_emoji} تغییر 30 روزه: {change_percent:+.2f}%\n\n"
                else:
                    message += f"{metal_name.upper()}:\n"
                    message += "⚠️ داده‌ای دریافت نشد\n\n"
            
            message += "🔄 به روزرسانی بعدی: 4 ساعت دیگر\n"
            message += "#گزارش_روزانه #فلزات"
            
            return message
        except Exception as e:
            logging.error(f"خطا در تولید گزارش روزانه: {e}")
            return "خطا در تولید گزارش روزانه"
    
    def analyze_metal(self, metal_name: str) -> str:
        """تحلیل کامل یک فلز"""
        try:
            symbol = self.metals.get(metal_name)
            if not symbol:
                return f"فلز {metal_name} یافت نشد"
            
            data = self.get_metal_data(symbol, '5d')
            if data is None or len(data) < 50:
                return f"داده کافی برای {metal_name} موجود نیست"
            
            indicators = self.calculate_indicators(data)
            if not indicators:
                return f"خطا در محاسبه اندیکاتورهای {metal_name}"
            
            # استفاده از iloc به جای [] برای جلوگیری از هشدار
            indicators['current_price'] = data['Close'].iloc[-1] if len(data) > 0 else 0
            
            trend_analysis = self.analyze_trend(data)
            
            market_direction, confidence, action, signals_detail = self.get_signal_strength(indicators, trend_analysis)
            
            # تولید پیام تحلیل
            message = f"🔍 تحلیل {metal_name.upper()} - تایم‌فریم 15 دقیقه\n\n"
            message += f"💰 قیمت فعلی: ${indicators['current_price']:.2f}\n"
            message += f"📊 جهت بازار: {market_direction}\n"
            message += f"🎯 عمل پیشنهادی: {action}\n"
            message += f"🛡️ اطمینان تحلیل: {confidence}%\n\n"
            
            message += "📈 جزئیات اندیکاتورها:\n"
            for indicator_name, signal in signals_detail.items():
                emoji = "✅" if signal == action else "➖" if signal == "خنثی" else "❌"
                message += f"{emoji} {indicator_name}: {signal}\n"
            
            message += f"\n📊 RSI: {indicators.get('rsi', 0):.1f}"
            message += f"\n📊 موقعیت در بولینگر: {indicators.get('bb_position', 0.5)*100:.1f}%"
            message += f"\n💪 قدرت روند: {trend_analysis.get('trend_strength', 0)*100:.1f}%"
            
            message += f"\n\n⏰ زمان تحلیل: {datetime.now().strftime('%H:%M')}"
            message += f"\n🔄 به روزرسانی بعدی: 4 ساعت دیگر"
            message += f"\n#{metal_name}_تحلیل #سیگنال"
            
            return message
        except Exception as e:
            logging.error(f"خطا در تحلیل {metal_name}: {e}")
            return f"خطا در تحلیل {metal_name}"
    
    def send_telegram_message(self, message: str):
        """ارسال پیام به تلگرام"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.channel_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            logging.info(f"ارسال پیام به تلگرام (طول: {len(message)} کاراکتر)")
            response = requests.post(url, data=payload, timeout=30)
            
            if response.status_code == 200:
                logging.info("✅ پیام با موفقیت ارسال شد")
                return True
            else:
                error_msg = response.json().get('description', 'Unknown error')
                logging.error(f"❌ خطا در ارسال پیام: {response.status_code} - {error_msg}")
                return False
                
        except requests.exceptions.Timeout:
            logging.error("⏰ Timeout در ارسال پیام به تلگرام")
            return False
        except requests.exceptions.ConnectionError:
            logging.error("🔌 Connection Error در ارسال پیام به تلگرام")
            return False
        except Exception as e:
            logging.error(f"🚨 خطای غیرمنتظره در ارسال پیام: {e}")
            return False
    
    def run_analysis(self):
        """اجرای تحلیل اصلی"""
        try:
            logging.info("🚀 شروع تحلیل...")
            
            if not self.should_analyze():
                logging.info("⏸️ تحلیل لغو شد - بازار تعطیل است")
                return
            
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            
            logging.info(f"🕒 زمان فعلی: {current_hour}:{current_minute:02d}")
            
            # گزارش روزانه ساعت 4:30
            if current_hour == 4 and current_minute >= 30:
                logging.info("📊 ارسال گزارش روزانه...")
                daily_report = self.get_daily_summary()
                success = self.send_telegram_message(daily_report)
                if success:
                    logging.info("✅ گزارش روزانه ارسال شد")
                else:
                    logging.error("❌ خطا در ارسال گزارش روزانه")
            
            # تحلیل هر 4 ساعت از 5 صبح
            analysis_hours = [5, 9, 13, 17, 21]
            if current_hour in analysis_hours:
                logging.info("🔍 شروع تحلیل فلزات...")
                
                # تحلیل طلا
                gold_analysis = self.analyze_metal('gold')
                success_gold = self.send_telegram_message(gold_analysis)
                if success_gold:
                    logging.info("✅ تحلیل طلا ارسال شد")
                else:
                    logging.error("❌ خطا در ارسال تحلیل طلا")
                
                # فاصله بین ارسال پیام‌ها
                time.sleep(5)
                
                # تحلیل نقره
                silver_analysis = self.analyze_metal('silver')
                success_silver = self.send_telegram_message(silver_analysis)
                if success_silver:
                    logging.info("✅ تحلیل نقره ارسال شد")
                else:
                    logging.error("❌ خطا در ارسال تحلیل نقره")
            
            logging.info("🎉 تحلیل با موفقیت تکمیل شد")
            
        except Exception as e:
            logging.error(f"💥 خطای کلی در اجرای برنامه: {e}")

def main():
    try:
        analyzer = MetalMarketAnalyzer()
        analyzer.run_analysis()
    except ValueError as e:
        logging.error(f"❌ خطا در تنظیمات: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"💥 خطای غیرمنتظره: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
