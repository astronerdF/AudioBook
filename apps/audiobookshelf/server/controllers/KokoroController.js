const Logger = require('../Logger')
const KokoroClient = require('../clients/KokoroClient')

class KokoroController {
  constructor() {}

  ensureConfigured(res) {
    if (!global.KokoroApiBaseUrl) {
      res.status(503).send('Kokoro API base URL is not configured')
      return false
    }
    return true
  }

  async listAligners(_req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const payload = await KokoroClient.listAligners()
      res.json(payload)
    } catch (error) {
      this.handleError('listAligners', error, res)
    }
  }

  async listBooks(_req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const books = await KokoroClient.listBooks()
      res.json(books)
    } catch (error) {
      this.handleError('listBooks', error, res)
    }
  }

  async getBook(req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const book = await KokoroClient.getBook(req.params.bookId)
      res.json(book)
    } catch (error) {
      this.handleError('getBook', error, res)
    }
  }

  async deleteBook(req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const result = await KokoroClient.deleteBook(req.params.bookId)
      res.json(result)
    } catch (error) {
      this.handleError('deleteBook', error, res)
    }
  }

  async getChapterMetadata(req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const metadata = await KokoroClient.getChapterMetadata(req.params.bookId, req.params.chapterIndex)
      res.json(metadata)
    } catch (error) {
      this.handleError('getChapterMetadata', error, res)
    }
  }

  async streamChapterAudio(req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const response = await KokoroClient.streamChapterAudio(req.params.bookId, req.params.chapterIndex)
      Object.entries(response.headers || {}).forEach(([key, value]) => {
        const lower = key.toLowerCase()
        if (lower === 'transfer-encoding') return
        res.setHeader(key, value)
      })
      res.status(response.status)
      response.data.on('error', (error) => {
        Logger.error(`[KokoroController] streamChapterAudio pipe error`, error)
        res.destroy(error)
      })
      response.data.pipe(res)
    } catch (error) {
      this.handleError('streamChapterAudio', error, res)
    }
  }

  async getTask(req, res) {
    if (!this.ensureConfigured(res)) return
    try {
      const task = await KokoroClient.getTask(req.params.taskId)
      res.json(task)
    } catch (error) {
      this.handleError('getTask', error, res)
    }
  }

  async createAudiobook(req, res) {
    if (!this.ensureConfigured(res)) return
    if (!req.files || !req.files.file) {
      return res.status(400).send('Missing EPUB file upload')
    }

    const file = req.files.file
    const fields = {
      voice: req.body.voice,
      device: req.body.device,
      alignment_backend: req.body.alignment_backend,
      chapter_start: req.body.chapter_start,
      chapter_end: req.body.chapter_end
    }

    try {
      const payload = await KokoroClient.createAudiobook({ file, fields })
      res.status(202).json(payload)
    } catch (error) {
      this.handleError('createAudiobook', error, res)
    }
  }

  async requireAdmin(req, res, next) {
    if (!req.user?.isAdminOrUp) {
      return res.sendStatus(403)
    }
    next()
  }

  handleError(tag, error, res) {
    const status = error?.response?.status || 502
    const message = error?.response?.data || error?.message || 'Unexpected Kokoro API error'
    Logger.error(`[KokoroController] ${tag} failed`, error)
    if (typeof message === 'string') {
      res.status(status).send(message)
    } else {
      res.status(status).json(message)
    }
  }
}

module.exports = new KokoroController()
