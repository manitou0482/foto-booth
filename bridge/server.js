const {
    default: makeWASocket,
    DisconnectReason,
    useMultiFileAuthState,
} = require('@whiskeysockets/baileys')
const pino = require('pino')
const express = require('express')

const PORT   = process.env.PORT   || 3000
const SECRET = process.env.BRIDGE_SECRET || 'wonderbox'

const app = express()
app.use(express.json())

let sock        = null
let isConnected = false

async function connect() {
    const { state, saveCreds } = await useMultiFileAuthState('wa_session')

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
        logger: pino({ level: 'silent' }),
    })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            console.log('\n>>> QR-Code oben scannen, dann warten...\n')
        }
        if (connection === 'open') {
            isConnected = true
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

// Nachricht senden
app.post('/send', async (req, res) => {
    if (req.headers['x-secret'] !== SECRET) {
        return res.status(401).json({ ok: false, error: 'Unauthorized' })
    }
    if (!isConnected || !sock) {
        return res.status(503).json({ ok: false, error: 'WhatsApp nicht verbunden' })
    }

    const { phone, imageUrl } = req.body
    if (!phone || !imageUrl) {
        return res.status(400).json({ ok: false, error: 'phone und imageUrl erforderlich' })
    }

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

// Status-Check
app.get('/health', (_, res) => res.json({ connected: isConnected }))

app.listen(PORT, () => {
    console.log(`\n🚀 Wonderbox WhatsApp-Bridge läuft auf Port ${PORT}`)
    console.log(`   Secret: ${SECRET}\n`)
})

connect()
