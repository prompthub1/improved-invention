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

# تنظیمات اولیه
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MetalMarketAnalyzer:
    def __init__(self):
        # دریافت توکن و آیدی از environment variables
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
        
        if not self.bot_token or not self.channel_id:
            raise ValueError("لطفا TELEGRAM_BOT_TOKEN و TELEGRAM_CHANNEL_ID را تنظیم کنید")
            
        self.metals = {
            'gold': 'GC=F',
            'silver': 'SI=F'
        }
        
    def is_holiday(self, date: datetime) -> bool:
        """بررسی تعطیلی بازار"""
        holidays = [
            '2024-01-01', '2024-01-15', '2024-02-19', '2024-03-29',
            '2024-05-27', '2024-07-04', '2024-09-02', '2024-11-28',
            '2024-12-25'
        ]
        return date.strftime('%Y-%m-%d') in holidays
    
    def is_weekend(self, date: datetime) -> bool:
        """بررسی آخر هفته"""
        return date.weekday() >= 5
    
    def should_analyze(self) -> bool:
        """بررسی زمان تحلیل"""
        now = datetime.now()
        
        # بررسی تعطیلی
        if self.is_holiday(now) or self.is_weekend(now):
            logging.info("امروز بازار تعطیل است")
            return False
            
        # بررسی ساعات کاری (5 صبح تا 9 شب)
        current_hour = now.hour
        if current_hour < 5 or current_hour > 21:
            logging.info("خارج از ساعات کاری بازار")
            return False
            
        return True
    
    def get_metal_data(self, symbol: str, period: str = '1mo') -> pd.DataFrame:
        """دریافت داده‌های فلز"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval='15m')
            return data
        except Exception as e:
            logging.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def calculate_indicators(self, data: pd.DataFrame) -> Dict:
        """محاسبه اندیکاتورهای تکنیکال"""
        if len(data) < 50:
            return {}
        
        close_prices = data['Close'].values
        high_prices = data['High'].values
        low_prices = data['Low'].values
        
        # محاسبه اندیکاتورها
        indicators = {}
        
        # RSI
        indicators['rsi'] = talib.RSI(close_prices, timeperiod=14)[-1]
        
        # Moving Averages
        indicators['sma_20'] = talib.SMA(close_prices, timeperiod=20)[-1]
        indicators['sma_50'] = talib.SMA(close_prices, timeperiod=50)[-1]
        
        # MACD
        macd, macd_signal, macd_hist = talib.MACD(close_prices)
        indicators['macd'] = macd[-1]
        indicators['macd_signal'] = macd_signal[-1]
        indicators['macd_hist'] = macd_hist[-1]
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close_prices, timeperiod=20, nbdevup=2, nbdevdn=2)
        indicators['bb_upper'] = bb_upper[-1]
        indicators['bb_middle'] = bb_middle[-1]
        indicators['bb_lower'] = bb_lower[-1]
        indicators['bb_position'] = (close_prices[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1])
        
        return indicators
    
    def analyze_trend(self, data: pd.DataFrame) -> Dict:
        """تحلیل روند و سقف/کف‌ها"""
        if len(data) < 20:
            return {}
        
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
    
    def get_signal_strength(self, indicators: Dict, trend_analysis: Dict) -> Tuple[str, float, str]:
        """محاسبه قدرت سیگنال"""
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
    
    def get_daily_summary(self) -> str:
        """گزارش روزانه قیمت فلزات"""
        try:
            message = "📊 گزارش روزانه فلزات 📊\n\n"
            message += f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            
            for metal_name, symbol in self.metals.items():
                data_30d = self.get_metal_data(symbol, '1mo')
                if data_30d is not None and len(data_30d) > 0:
                    current_price = data_30d['Close'][-1]
                    price_30d_ago = data_30d['Close'][0]
                    change_percent = ((current_price - price_30d_ago) / price_30d_ago) * 100
                    
                    change_emoji = "📈" if change_percent > 0 else "📉"
                    
                    message += f"{metal_name.upper()}:\n"
                    message += f"💰 قیمت فعلی: ${current_price:.2f}\n"
                    message += f"{change_emoji} تغییر 30 روزه: {change_percent:+.2f}%\n\n"
            
            message += "🔄 به روزرسانی بعدی: 4 ساعت دیگر\n"
            message += "#گزارش_روزانه #فلزات"
            
            return message
        except Exception as e:
            logging.error(f"Error generating daily summary: {e}")
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
            indicators['current_price'] = data['Close'][-1]
            
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
            
            message += f"\n📊 RSI: {indicators['rsi']:.1f}"
            message += f"\n📊 موقعیت در بولینگر: {indicators['bb_position']*100:.1f}%"
            message += f"\n💪 قدرت روند: {trend_analysis['trend_strength']*100:.1f}%"
            
            message += f"\n\n⏰ زمان تحلیل: {datetime.now().strftime('%H:%M')}"
            message += f"\n🔄 به روزرسانی بعدی: 4 ساعت دیگر"
            message += f"\n#{metal_name}_تحلیل #سیگنال"
            
            return message
        except Exception as e:
            logging.error(f"Error analyzing {metal_name}: {e}")
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
            response = requests.post(url, data=payload)
            if response.status_code == 200:
                logging.info("پیام با موفقیت ارسال شد")
            else:
                logging.error(f"خطا در ارسال پیام: {response.status_code}")
        except Exception as e:
            logging.error(f"Error sending Telegram message: {e}")
    
    def run_analysis(self):
        """اجرای تحلیل اصلی"""
        if not self.should_analyze():
            logging.info("تحلیل لغو شد - بازار تعطیل است")
            return
        
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        
        # گزارش روزانه ساعت 4:30
        if current_hour == 4 and current_minute >= 30:
            logging.info("ارسال گزارش روزانه...")
            daily_report = self.get_daily_summary()
            self.send_telegram_message(daily_report)
        
        # تحلیل هر 4 ساعت از 5 صبح
        analysis_hours = [5, 9, 13, 17, 21]
        if current_hour in analysis_hours:
            logging.info("شروع تحلیل فلزات...")
            
            # تحلیل طلا
            gold_analysis = self.analyze_metal('gold')
            self.send_telegram_message(gold_analysis)
            
            # فاصله بین ارسال پیام‌ها
            time.sleep(10)
            
            # تحلیل نقره
            silver_analysis = self.analyze_metal('silver')
            self.send_telegram_message(silver_analysis)
        
        logging.info("تحلیل заверш شد")

def main():
    try:
        analyzer = MetalMarketAnalyzer()
        analyzer.run_analysis()
    except Exception as e:
        logging.error(f"خطا در اجرای برنامه: {e}")

if __name__ == "__main__":
    main()
