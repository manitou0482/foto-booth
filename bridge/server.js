const {
    default: makeWASocket,
    DisconnectReason,
    useMultiFileAuthState,
} = require('@whiskeysockets/baileys')
const pino   = require('pino')
const QRCode = require('qrcode')
const express = require('express')

const PORT   = process.env.PORT   || 3000
const SECRET = process.env.BRIDGE_SECRET || 'wonderbox'

const app = express()
app.use(express.json())

let sock        = null
let isConnected = false
let currentQR   = null

async function connect() {
    const { state, saveCreds } = await useMultiFileAuthState('wa_session')

    sock = makeWASocket({
        auth: state,
        logger: pino({ level: 'silent' }),
    })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            currentQR = qr
            console.log('\n>>> QR-Code bereit!')
            console.log('>>> Im Browser öffnen: http://localhost:3000/qr\n')
        }
        if (connection === 'open') {
            isConnected = true
            currentQR   = null
            console.log('✅ WhatsApp verbunden – Bridge ist bereit.')
        }
        if (connection === 'close') {
            isConnected = false
            const code = lastDisconnect?.error?.output?.statusCode
            const loggedOut = code === DisconnectReason.loggedOut
            console.log(loggedOut ? '❌ Abgemeldet.' : '🔄 Verbindung unterbrochen, wird neu verbunden...')
            if (!loggedOut) connect()
        }
    })
}

// QR-Code als Bild im Browser anzeigen
app.get('/qr', async (_, res) => {
    if (isConnected) return res.send('<h2>✅ WhatsApp bereits verbunden!</h2>')
    if (!currentQR)  return res.send('<p>Warte auf QR-Code... Seite neu laden.</p>')
    const svg = await QRCode.toString(currentQR, { type: 'svg', width: 300 })
    res.setHeader('Content-Type', 'text/html')
    res.send(`<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>Wonderbox QR</title></head>
<body style="font-family:sans-serif;text-align:center;padding:40px">
<h2>Mit WhatsApp scannen</h2>
<p>Einstellungen → Verknüpfte Geräte → Gerät hinzufügen</p>
${svg}
<p style="color:gray;font-size:0.8em">Seite aktualisiert sich automatisch</p>
</body></html>`)
})

// Status-Check
app.get('/health', (_, res) => res.json({ connected: isConnected }))

// Nachricht senden
app.post('/send', async (req, res) => {
    if (req.headers['x-secret'] !== SECRET)
        return res.status(401).json({ ok: false, error: 'Unauthorized' })
    if (!isConnected || !sock)
        return res.status(503).json({ ok: false, error: 'WhatsApp nicht verbunden' })

    const { phone, imageUrl } = req.body
    if (!phone || !imageUrl)
        return res.status(400).json({ ok: false, error: 'phone und imageUrl erforderlich' })

    const jid = phone.replace(/\D/g, '') + '@s.whatsapp.net'
    try {
        await sock.sendMessage(jid, {
            image: { url: imageUrl },
            caption: 'Dein Wonderbox-Foto! ✨',
        })
        res.json({ ok: true })
    } catch (e) {
        res.status(500).json({ ok: false, error: e.message })
    }
})

app.listen(PORT, () => {
    console.log(`\n🚀 Wonderbox WhatsApp-Bridge läuft auf Port ${PORT}`)
    console.log(`   Secret: ${SECRET}\n`)
})

connect()
