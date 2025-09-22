const axios = require('axios')
const FormData = require('form-data')
const fs = require('fs')

const Logger = require('../Logger')

class KokoroClient {
  constructor() {
    this.timeout = Number(process.env.KOKORO_API_TIMEOUT || 600000)
  }

  get baseUrl() {
    const url = (global.KokoroApiBaseUrl || 'http://127.0.0.1:8000/api').trim()
    if (!url) {
      throw new Error('Kokoro API base URL is not configured')
    }
    return url.replace(/\/+$/, '')
  }

  async listAligners() {
    return this._get('/aligners')
  }

  async listBooks() {
    return this._get('/books')
  }

  async getBook(bookId) {
    return this._get(`/books/${encodeURIComponent(bookId)}`)
  }

  async deleteBook(bookId) {
    return this._delete(`/books/${encodeURIComponent(bookId)}`)
  }

  async getChapterMetadata(bookId, chapterIndex) {
    return this._get(`/books/${encodeURIComponent(bookId)}/chapters/${chapterIndex}/metadata`)
  }

  async streamChapterAudio(bookId, chapterIndex) {
    return this._stream(`/books/${encodeURIComponent(bookId)}/chapters/${chapterIndex}/audio`)
  }

  async getTask(taskId) {
    return this._get(`/tasks/${encodeURIComponent(taskId)}`)
  }

  async createAudiobook(options) {
    const { file, fields } = options
    if (!file) {
      throw new Error('Missing file payload')
    }

    const form = new FormData()

    const stream = this._getFileStream(file)
    form.append('file', stream, {
      filename: file.name || 'book.epub',
      contentType: file.mimetype || 'application/epub+zip'
    })

    Object.entries(fields || {})
      .filter(([, value]) => value !== undefined && value !== null && value !== '')
      .forEach(([key, value]) => {
        form.append(key, value)
      })

    try {
      const response = await axios.post(`${this.baseUrl}/audiobooks`, form, {
        headers: form.getHeaders(),
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
        timeout: this.timeout
      })
      return response.data
    } finally {
      this._cleanupTempFile(file)
    }
  }

  async _get(path) {
    const response = await axios.get(`${this.baseUrl}${path}`, {
      timeout: this.timeout
    })
    return response.data
  }

  async _delete(path) {
    const response = await axios.delete(`${this.baseUrl}${path}`, {
      timeout: this.timeout
    })
    return response.data
  }

  async _stream(path) {
    const response = await axios.get(`${this.baseUrl}${path}`, {
      responseType: 'stream',
      timeout: this.timeout
    })
    return response
  }

  _getFileStream(file) {
    if (file.tempFilePath && fs.existsSync(file.tempFilePath)) {
      return fs.createReadStream(file.tempFilePath)
    }
    if (file.data) {
      return file.data
    }
    throw new Error('Unable to access uploaded file contents')
  }

  _cleanupTempFile(file) {
    if (file?.tempFilePath) {
      fs.promises
        .unlink(file.tempFilePath)
        .catch((error) => Logger.debug(`[KokoroClient] Failed to cleanup temp file ${file.tempFilePath}: ${error?.message}`))
    }
  }
}

module.exports = new KokoroClient()
