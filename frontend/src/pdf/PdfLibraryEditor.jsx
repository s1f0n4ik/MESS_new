import { useState } from 'react'
import { apiUrl, pdfUrl } from '../net/urls'
import { PdfDocument } from './PdfDocument'
import { PdfEditorToolbar, usePdfEditor } from './PdfEditor'

const FILES = [1, 2, 3, 4].map((number) => ({
  file: `pdf${number}.pdf`,
  slot: `pdf${number}`,
  defaultLabel: `Документ ${number}`,
}))

export function PdfLibraryEditor({ serverHost, state, updatedBy, onClose }) {
  const [activeFile, setActiveFile] = useState(FILES[0].file)
  const [titleOverrides, setTitleOverrides] = useState({})
  const [titleDraft, setTitleDraft] = useState(state?.media?.pdfTitles?.pdf1 || FILES[0].defaultLabel)
  const [titleError, setTitleError] = useState('')
  const [titleSaving, setTitleSaving] = useState(false)
  const selectedFile = FILES.find((item) => item.file === activeFile) || FILES[0]
  const titles = { ...(state?.media?.pdfTitles || {}), ...titleOverrides }
  const titleFor = (item) => titles[item.slot] || item.defaultLabel
  const selectedTitle = titleFor(selectedFile)
  const externalRevision = state?.pdfEditor?.[selectedFile.slot]?.revision
  const editor = usePdfEditor(selectedFile.slot, serverHost, externalRevision, updatedBy)
  const mtime = state?.media?.pdfs?.[selectedFile.slot]?.mtime
  const baseUrl = pdfUrl(selectedFile.file, serverHost)
  const activeUrl = mtime ? `${baseUrl}?v=${mtime}` : baseUrl

  const selectFile = (item) => {
    setActiveFile(item.file)
    setTitleDraft(titleFor(item))
    setTitleError('')
  }

  const saveTitle = async () => {
    const value = titleDraft.trim()
    if (!value || value === selectedTitle) return
    setTitleSaving(true); setTitleError('')
    try {
      const response = await fetch(apiUrl(`/api/media/pdf/${selectedFile.slot}/title`, serverHost), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: value }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`)
      const saved = data.pdfTitles?.[selectedFile.slot] || value
      setTitleOverrides((current) => ({ ...current, [selectedFile.slot]: saved }))
      setTitleDraft(saved)
    } catch (reason) {
      setTitleError(reason.message || String(reason))
    } finally {
      setTitleSaving(false)
    }
  }

  const close = async () => {
    if (editor.editMode) {
      const saved = await editor.exitEdit()
      if (!saved) return
    }
    onClose()
  }

  return (
    <div className="pdf-library-editor">
      <div className="pdf-library-editor__tabs">
        {FILES.map((item) => (
          <button key={item.file} disabled={editor.editMode}
            className={item.file === activeFile ? 'is-active' : ''}
            onClick={() => selectFile(item)}>
            {titleFor(item)}
          </button>
        ))}
        <label className="pdf-library-editor__title">
          Название вкладки
          <input value={titleDraft} maxLength={80} disabled={titleSaving || editor.editMode}
            onChange={(event) => setTitleDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); saveTitle() } }} />
          <button onClick={saveTitle} disabled={titleSaving || editor.editMode || !titleDraft.trim()}>
            {titleSaving ? '…' : 'Сохранить'}
          </button>
        </label>
        <button onClick={close}>Закрыть</button>
      </div>
      {titleError && <div className="pdf-editor-error pdf-editor-error--block">Название: {titleError}</div>}
      <PdfEditorToolbar editor={editor} />
      <div className="pdf-library-editor__document">
        <PdfDocument key={activeFile} url={activeUrl} resetKey={activeFile}
          editor={{ pages: editor.doc.pages, editMode: editor.editMode, selected: editor.selected,
            assetOrigin: editor.assetOrigin, onSelect: editor.select, onChange: editor.update }} />
      </div>
    </div>
  )
}
