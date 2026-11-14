import io
import csv
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from pypdf import PdfReader
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)

# --- KEEP-ALIVE SERVER (Render Free Tier ke liye taaki bot disconnect na ho) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Elite Quiz Bot is Alive and Running!")

def run_health_server():
    server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
    server.serve_forever()

# Background thread mein server chalayenge
threading.Thread(target=run_health_server, daemon=True).start()

quizzes = {}
user_defaults = {}

# States for Quiz Creation
GET_TITLE, GET_NEGATIVE, GET_SPEED, GET_SPLIT, GET_FILE = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith('play_'):
        quiz_id = context.args[0].replace('play_', '')
        if quiz_id in quizzes:
            await update.message.reply_text(f"🚀 DM mein Quiz shuru ho rahi hai! (Quiz ID: {quiz_id})")
            context.args = [quiz_id]
            await play_quiz(update, context)
            return

    await update.message.reply_text(
        "👋 **Welcome to Elite Quiz Bot!**\n\n"
        "✨ **Main Commands:**\n"
        "/create - Naya interactive button-based quiz banayein (.txt, .pdf, .csv, .html)\n"
        "/setdefault - Apni default settings set karein\n"
        "/list - Saare available quizzes dekhein\n"
        "/stop - Chal rahi quiz ko rokne ke liye\n"
        "/play [ID] - Quiz khele"
    )

async def set_default_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚙️ **Default Settings Setup:**\n\n"
        "Pehle apni **Default Negative Marking** bhejiye (Jaise: `0`, `0.25`, `0.5`, ya `1`):"
    )
    context.user_data['setting_step'] = 'negative'
    return

async def list_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quizzes:
        await update.message.reply_text("📂 Filhal koi quiz available nahi hai. `/create` use karke naya quiz banayein!")
        return
    
    text = "📋 **Available Quizzes:**\n\n"
    for q_id, q_data in quizzes.items():
        text += (
            f"🆔 **Quiz ID:** `{q_id}`\n"
            f"📌 **Title:** {q_data['title']}\n"
            f"❓ **Questions:** {len(q_data['questions'])}\n"
            f"⚡ **Negative:** {q_data['negative']} | ⏱️ **Speed:** {q_data['speed_label']}\n"
            f"------------------\n"
        )
    text += "\nKhelne ke liye `/play [Quiz_ID]` use karein."
    await update.message.reply_text(text)

# --- QUIZ CREATION FLOW ---
async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Naya Quiz Banayein**\n\nPehle **Quiz ka Naam (Title)** likhkar bhejein:")
    return GET_TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quiz_title'] = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id in user_defaults:
        defaults = user_defaults[user_id]
        context.user_data['quiz_negative'] = defaults['negative']
        context.user_data['quiz_timer'] = defaults['timer']
        context.user_data['quiz_speed_label'] = defaults['speed_label']
        
        await update.message.reply_text(
            f"⚡ Aapki Saved Default Settings apply ho gayi hain:\n"
            f"• Negative: {defaults['negative']}\n"
            f"• Speed: {defaults['speed_label']}\n\n"
            f"🗂️ Kya 50 se zyada questions ko parts mein divide karna hai? (yes/no)"
        )
        return GET_SPLIT
    else:
        await update.message.reply_text("⚡ **Negative Marking** select karein (Jaise: `0`, `0.25`, `0.5`):")
        return GET_NEGATIVE

async def get_negative(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['quiz_negative'] = float(update.message.text.strip())
    except:
        context.user_data['quiz_negative'] = 0.0
    
    keyboard = [
        [InlineKeyboardButton("⚡ Fast (15s per Q)", callback_data="speed_fast")],
        [InlineKeyboardButton("🏃 Normal (30s per Q)", callback_data="speed_normal")],
        [InlineKeyboardButton("🚶 Slow (60s per Q)", callback_data="speed_slow")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⏱️ **Quiz Speed / Timer select karein:**", reply_markup=reply_markup)
    return GET_SPEED

async def get_speed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "speed_fast":
        context.user_data['quiz_timer'] = 15
        context.user_data['quiz_speed_label'] = "Fast (15s)"
    elif data == "speed_slow":
        context.user_data['quiz_timer'] = 60
        context.user_data['quiz_speed_label'] = "Slow (60s)"
    else:
        context.user_data['quiz_timer'] = 30
        context.user_data['quiz_speed_label'] = "Normal (30s)"
        
    await query.edit_message_text(
        f"✅ Speed Selected: {context.user_data['quiz_speed_label']}\n\n"
        f"🗂️ Agar file mein **50 se zyada questions** hon toh parts mein divide karein? (`yes` ya `no` likhkar bhejein)"
    )
    return GET_SPLIT

async def get_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.message.text.strip().lower()
    context.user_data['quiz_split'] = True if 'yes' in ans or 'haan' in ans else False
    
    await update.message.reply_text("📂 Ab apni **.txt, .pdf, .csv, ya .html** file chat mein upload karein!")
    return GET_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("⚠️ Kripya valid file upload karein.")
        return GET_FILE

    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()

    file_content = ""
    file_name = document.file_name.lower() if document.file_name else ""
    questions = []

    if file_name.endswith('.pdf'):
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    file_content += txt + "\n"
        except:
            await update.message.reply_text("❌ PDF read nahi ho saki.")
            return ConversationHandler.END

    elif file_name.endswith('.html') or file_name.endswith('.htm'):
        try:
            html_text = file_bytes.decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_text, 'html.parser')
            file_content = soup.get_text(separator='\n')
        except:
            await update.message.reply_text("❌ HTML read nahi ho saki.")
            return ConversationHandler.END

    elif file_name.endswith('.csv'):
        try:
            decoded_file = file_bytes.decode('utf-8', errors='ignore').splitlines()
            reader = csv.reader(decoded_file)
            for row in reader:
                if len(row) >= 6:
                    q_text = row[0].strip()
                    opts = [row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip()]
                    ans = row[5].strip().lower()
                    expl = row[6].strip() if len(row) > 6 else ""
                    questions.append({
                        "question": q_text,
                        "options": opts,
                        "answer": ans,
                        "explanation": expl
                    })
        except:
            pass

    else:
        try:
            file_content = file_bytes.decode('utf-8')
        except:
            file_content = file_bytes.decode('latin-1', errors='ignore')

    if not questions and file_content:
        blocks = file_content.split('Q')
        for block in blocks:
            if not block.strip():
                continue
            try:
                lines = [line.strip() for line in block.split('\n') if line.strip()]
                q_text = lines[0].split('. ', 1)[1] if '. ' in lines[0] else lines[0]
                
                options = []
                correct_ans = ""
                explanation = ""
                
                for line in lines[1:]:
                    if any(line.startswith(prefix) for prefix in ['(a)', '(b)', '(c)', '(d)', 'a)', 'b)', 'c)', 'd)']):
                        if '✅' in line:
                            correct_ans = line.replace('(', '').replace(')', '')[0].lower()
                        options.append(line.replace('✅', '').strip())
                    elif line.startswith('Ex:') or line.startswith('Explanation:'):
                        explanation = line.replace('Ex:', '').replace('Explanation:', '').strip()
                        
                if q_text and options and correct_ans:
                    questions.append({
                        "question": q_text,
                        "options": options,
                        "answer": correct_ans,
                        "explanation": explanation
                    })
            except:
                continue

    if not questions:
        await update.message.reply_text("❌ File se questions extract nahi ho paye. Format check karein.")
        return ConversationHandler.END

    title = context.user_data.get('quiz_title', 'Custom Quiz')
    negative = context.user_data.get('quiz_negative', 0.0)
    timer = context.user_data.get('quiz_timer', 30)
    speed_label = context.user_data.get('quiz_speed_label', 'Normal (30s)')
    should_split = context.user_data.get('quiz_split', False)
    bot_username = context.bot.username

    if should_split and len(questions) > 50:
        chunks = [questions[i:i + 50] for i in range(0, len(questions), 50)]
        for idx, chunk in enumerate(chunks):
            q_id = str(len(quizzes) + 1)
            part_title = f"{title} (Part {idx + 1})"
            quizzes[q_id] = {
                "title": part_title,
                "negative": negative,
                "timer": timer,
                "speed_label": speed_label,
                "questions": chunk
            }
            
            keyboard = [
                [InlineKeyboardButton("👤 Play in Private (DM)", url=f"https://t.me/{bot_username}?start=play_{q_id}")],
                [InlineKeyboardButton("📤 Share Quiz", url=f"https://t.me/share/url?url=Let's play this quiz: {part_title} (ID: {q_id}) &text=Play using /play {q_id}")],
                [InlineKeyboardButton("🌐 Open in Chrome (Mock Test)", url=f"https://example.com/mock-test/{q_id}")]
            ]
            await update.message.reply_text(
                f"✅ Created **{part_title}**!\n🆔 Quiz ID: `{q_id}`\n🔢 Questions: {len(chunk)}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        q_id = str(len(quizzes) + 1)
        quizzes[q_id] = {
            "title": title,
            "negative": negative,
            "timer": timer,
            "speed_label": speed_label,
            "questions": questions
        }

        keyboard = [
            [InlineKeyboardButton("👤 Play in Private (DM)", url=f"https://t.me/{bot_username}?start=play_{q_id}")],
            [InlineKeyboardButton("📤 Share Quiz", url=f"https://t.me/share/url?url=Let's play this quiz: {title} (ID: {q_id}) &text=Play using /play {q_id}")],
            [InlineKeyboardButton("🌐 Open in Chrome (Mock Test)", url=f"https://example.com/mock-test/{q_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ **Quiz Successfully Created!**\n\n"
            f"📌 Title: {title}\n"
            f"🔢 Total Questions: {len(questions)}\n"
            f"🆔 Quiz ID: `{q_id}`\n\n"
            f"Apne mode select karein:",
            reply_markup=reply_markup
        )
        
    return ConversationHandler.END

async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if f"playing_{user_id}" in context.user_data:
        del context.user_data[f"playing_{user_id}"]
        await update.message.reply_text("🛑 Quiz successfully rok di gayi hai!")
    else:
        await update.message.reply_text("❌ Koi active quiz nahi chal rahi hai.")
    return ConversationHandler.END

async def play_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Kripya Quiz ID dein. Jaise: `/play 1`")
        return
    
    quiz_id = args[0]
    if quiz_id not in quizzes:
        await update.message.reply_text("❌ Ye Quiz ID galat hai. `/list` check karein.")
        return
    
    quiz = quizzes[quiz_id]
    user_id = update.effective_user.id
    
    context.user_data[f"playing_{user_id}"] = {
        "quiz_id": quiz_id,
        "q_index": 0,
        "score": 0.0
    }
    
    await update.message.reply_text(f"🚀 Quiz Start: **{quiz['title']}**\n(Quiz rokne ke liye `/stop` dabayein)")
    await send_question_with_buttons(update, context)

async def send_question_with_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    play_data = context.user_data.get(f"playing_{user_id}")
    if not play_data:
        return
    
    quiz = quizzes[play_data["quiz_id"]]
    q_index = play_data["q_index"]
    
    if q_index >= len(quiz["questions"]):
        score = play_data["score"]
        total = len(quiz["questions"])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 **Quiz Complete!**\n\nAapka Score: **{score} / {total}**"
        )
        del context.user_data[f"playing_{user_id}"]
        return
    
    q_data = quiz["questions"][q_index]
    
    keyboard = []
    letters = ['a', 'b', 'c', 'd', 'e', 'f']
    for idx, opt in enumerate(q_data["options"]):
        opt_letter = letters[idx] if idx < len(letters) else str(idx+1)
        callback_data = f"ans_{play_data['quiz_id']}_{q_index}_{opt_letter}"
        keyboard.append([InlineKeyboardButton(opt, callback_data=callback_data)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❓ **Question {q_index + 1} of {len(quiz['questions'])}:**\n{q_data['question']}",
        reply_markup=reply_markup
    )

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("ans_"):
        return
        
    _, quiz_id, q_idx_str, user_ans = data.split("_")
    q_index = int(q_idx_str)
    user_id = update.effective_user.id
    
    play_key = f"playing_{user_id}"
    if play_key not in context.user_data:
        await query.edit_message_text("⚠️ Yeh quiz session expire ho chuka hai.")
        return
        
    play_data = context.user_data[play_key]
    if play_data["quiz_id"] != quiz_id or play_data["q_index"] != q_index:
        await query.edit_message_text("⚠️ Ye purana question hai.")
        return
        
    quiz = quizzes[quiz_id]
    q_data = quiz["questions"][q_index]
    negative_val = quiz.get("negative", 0.0)
    
    correct_ans = q_data["answer"].strip().lower()
    user_ans = user_ans.strip().lower()
    
    if user_ans == correct_ans:
        play_data["score"] += 1.0
        result_text = f"✅ **Sahi jawab!** ({user_ans.upper()})"
    else:
        play_data["score"] -= negative_val
        result_text = f"❌ **Galat jawab!** (-{negative_val}). Sahi option tha: *({correct_ans.upper()})*"
        
    explanation_text = ""
    if q_data.get("explanation"):
        explanation_text = f"\n\n💡 **Explanation:** {q_data['explanation']}"
        
    await query.edit_message_text(
        f"❓ **Question {q_index + 1}:** {q_data['question']}\n\n{result_text}{explanation_text}"
    )
    
    play_data["q_index"] += 1
    await send_question_with_buttons(update, context)

async def handle_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if context.user_data.get('setting_step') == 'negative':
        try:
            val = float(text)
        except:
            val = 0.0
        context.user_data['def_neg'] = val
        
        keyboard = [
            [InlineKeyboardButton("⚡ Fast (15s)", callback_data="def_speed_fast")],
            [InlineKeyboardButton("🏃 Normal (30s)", callback_data="def_speed_normal")],
            [InlineKeyboardButton("🚶 Slow (60s)", callback_data="def_speed_slow")]
        ]
        await update.message.reply_text("⏱️ Apni **Default Speed / Timer** select karein:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

async def handle_default_speed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if "fast" in data:
        timer_val, label = 15, "Fast (15s)"
    elif "slow" in data:
        timer_val, label = 60, "Slow (60s)"
    else:
        timer_val, label = 30, "Normal (30s)"
        
    user_defaults[user_id] = {
        "negative": context.user_data.get('def_neg', 0.0),
        "timer": timer_val,
        "speed_label": label
    }
    context.user_data['
