const {
    default: makeWASocket,
    DisconnectReason,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys')
const pino    = require('pino')
const express = require('express')

const PORT   = process.env.PORT           || 3000
const SECRET = process.env.BRIDGE_SECRET  || 'wonderbox'
const PHONE  = process.env.PHONE_NUMBER   || ''  // z.B. 4915512345678

const app = express()
app.use(express.json())

let sock        = null
let isConnected = false

async function connect() {
    const { state, saveCreds } = await useMultiFileAuthState('wa_session')
    const { version } = await fetchLatestBaileysVersion()

    sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: 'silent' }),
        // Pairing-Code-Modus statt QR
        mobile: false,
    })

    // Pairing Code anfordern falls noch nicht verbunden
    if (!state.creds.registered && PHONE) {
        setTimeout(async () => {
            try {
                const code = await sock.requestPairingCode(PHONE)
                console.log('\n╔══════════════════════════════╗')
                console.log(`║  Pairing Code: ${code}  ║`)
                console.log('╚══════════════════════════════╝')
                console.log('\nIn WhatsApp:')
                console.log('Einstellungen → Verknüpfte Geräte → Gerät hinzufügen')
                console.log('→ "Mit Telefonnummer verknüpfen" → Code eingeben\n')
            } catch (e) {
                console.log('Pairing-Code-Fehler:', e.message)
            }
        }, 3000)
    } else if (!state.creds.registered && !PHONE) {
        console.log('\n⚠️  PHONE_NUMBER nicht gesetzt!')
        console.log('Starte mit: PHONE_NUMBER=4915512345678 node server.js\n')
    }

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', ({ connection, lastDisconnect }) => {
        if (connection === 'open') {
            isConnected = true
            console.log('✅ WhatsApp verbunden – Bridge ist bereit.')
        }
        if (connection === 'close') {
            isConnected = false
            const err     = lastDisconnect?.error
            const code    = err?.output?.statusCode
            const loggedOut = code === DisconnectReason.loggedOut
            console.log(`🔴 Verbindung getrennt – Code: ${code}, Fehler: ${err?.message || err}`)
            if (!loggedOut) connect()
        }
    })
}

app.get('/health', (_, res) => res.json({ connected: isConnected }))

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
