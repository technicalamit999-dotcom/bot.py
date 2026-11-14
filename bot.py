import io
import logging
from pypdf import PdfReader
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)

quizzes = {}
user_defaults = {}  # User ki default settings store karne ke liye

# States for Quiz Creation
GET_TITLE, GET_NEGATIVE, GET_TIMER, GET_SHUFFLE, GET_EXPLAIN, GET_SPLIT, GET_FILE = range(7)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Welcome to Elite Quiz Bot!**\n\n"
        "✨ **Main Commands:**\n"
        "/create - Naya quiz banayein\n"
        "/setdefault - Apni default settings set karein (Timer, Negative, etc.)\n"
        "/list - Saare available quizzes dekhein\n"
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
            f"⚡ **Negative:** {q_data['negative']} | ⏱️ **Timer:** {q_data['timer']}s\n"
            f"------------------\n"
        )
    text += "\nKhelne ke liye `/play [Quiz_ID]` ya niche diye buttons use karein."
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
        context.user_data['quiz_shuffle'] = defaults['shuffle']
        context.user_data['quiz_explain'] = defaults['explain']
        
        await update.message.reply_text(
            f"⚡ Aapki Saved Default Settings apply ho gayi hain:\n"
            f"• Negative: {defaults['negative']}\n"
            f"• Timer: {defaults['timer']}s\n\n"
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
    
    await update.message.reply_text("⏱️ **Timer per Question:** Seconds likhein (Jaise: `30`):")
    return GET_TIMER

async def get_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['quiz_timer'] = int(update.message.text.strip())
    except:
        context.user_data['quiz_timer'] = 30
        
    await update.message.reply_text("🔀 **Shuffle Questions?** (yes/no):")
    return GET_SHUFFLE

async def get_shuffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.message.text.strip().lower()
    context.user_data['quiz_shuffle'] = True if 'yes' in ans or 'haan' in ans else False
    
    await update.message.reply_text("💡 **Show Explanations?** (yes/no):")
    return GET_EXPLAIN

async def get_explain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.message.text.strip().lower()
    context.user_data['quiz_explain'] = True if 'yes' in ans or 'haan' in ans else False
    
    await update.message.reply_text("🗂️ Agar **50 se zyada questions** hon toh parts mein divide karein? (yes/no)")
    return GET_SPLIT

async def get_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.message.text.strip().lower()
    context.user_data['quiz_split'] = True if 'yes' in ans or 'haan' in ans else False
    
    await update.message.reply_text("📂 Ab apni **.txt** ya **.pdf** file chat mein upload karein!")
    return GET_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("⚠️ Kripya valid .txt ya .pdf file upload karein.")
        return GET_FILE

    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()

    file_content = ""
    file_name = document.file_name.lower() if document.file_name else ""

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
    else:
        try:
            file_content = file_bytes.decode('utf-8')
        except:
            file_content = file_bytes.decode('latin-1', errors='ignore')

    questions = []
    blocks = file_content.split('Q')
    
    for block in blocks:
        if not block.strip():
            continue
        try:
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            q_text = lines[0].split('. ', 1)[1] if '. ' in lines[0] else lines[0]
            
            options = []
            correct_idx = 0
            explanation = ""
            
            for line in lines[1:]:
                if any(line.startswith(prefix) for prefix in ['(a)', '(b)', '(c)', '(d)', 'a)', 'b)', 'c)', 'd)']):
                    if '✅' in line:
                        correct_idx = len(options)
                    clean_opt = line.replace('✅', '').strip()
                    options.append(clean_opt)
                elif line.startswith('Ex:') or line.startswith('Explanation:'):
                    explanation = line.replace('Ex:', '').replace('Explanation:', '').strip()
                    
            if q_text and len(options) >= 2:
                questions.append({
                    "question": q_text,
                    "options": options,
                    "correct": correct_idx,
                    "explanation": explanation
                })
        except:
            continue

    if not questions:
        await update.message.reply_text("❌ Questions extract nahi ho paye.")
        return ConversationHandler.END

    title = context.user_data.get('quiz_title', 'Custom Quiz')
    negative = context.user_data.get('quiz_negative', 0.0)
    timer = context.user_data.get('quiz_timer', 30)

    q_id = str(len(quizzes) + 1)
    quizzes[q_id] = {
        "title": title,
        "negative": negative,
        "timer": timer,
        "questions": questions
    }

    # Action Buttons (Private, Group, Chrome Mock Test)
    keyboard = [
        [InlineKeyboardButton("👤 Play in Private (DM)", url=f"https://t.me/{context.bot.username}?start=play_{q_id}")],
        [InlineKeyboardButton("👥 Play in Group", url=f"https://t.me/share/url?url=Let's play quiz {title}! ID: {q_id}")],
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action cancelled.")
    return ConversationHandler.END

async def handle_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if context.user_data.get('setting_step') == 'negative':
        try:
            val = float(text)
        except:
            val = 0.0
        context.user_data['def_neg'] = val
        context.user_data['setting_step'] = 'timer'
        await update.message.reply_text("⏱️ Ab apne **Default Timer (seconds)** bhejiye (Jaise: `30`):")
        return

    elif context.user_data.get('setting_step') == 'timer':
        try:
            val = int(text)
        except:
            val = 30
        
        user_defaults[user_id] = {
            "negative": context.user_data.get('def_neg', 0.0),
            "timer": val,
            "shuffle": True,
            "explain": True
        }
        context.user_data['setting_step'] = None
        await update.message.reply_text("✅ **Aapki Default Settings Successfully Save ho gayi hain!** Ab `/create` karne par yeh automatically use hongi.")
        return

if __name__ == '__main__':
    TOKEN = '9269979361:AAGk8w47dP8oGijvRVuRDNvnCLMXlWA-HuU'
    
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('create', create_start)],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_title)],
            GET_NEGATIVE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_negative)],
            GET_TIMER: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_timer)],
            GET_SHUFFLE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_shuffle)],
            GET_EXPLAIN: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_explain)],
            GET_SPLIT: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_split)],
            GET_FILE: [MessageHandler(filters.Document.ALL, receive_file)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setdefault", set_default_start))
    application.add_handler(CommandHandler("list", list_quizzes))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message_router))

    print("Elite Quiz Bot started successfully...")
    application.run_polling()
