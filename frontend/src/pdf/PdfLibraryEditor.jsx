import { useMemo, useState } from 'react'
import { pdfUrl } from '../net/urls'
import { PdfDocument } from './PdfDocument'
import { PdfEditorToolbar, usePdfEditor } from './PdfEditor'

const FILES = [1, 2, 3, 4].map((number) => ({
  file: `pdf${number}.pdf`,
  slot: `pdf${number}`,
  label: `Текст ${number}`,
}))

export function PdfLibraryEditor({ serverHost, state, updatedBy, onClose }) {
  const [activeFile, setActiveFile] = useState(FILES[0].file)
  const selectedFile = FILES.find((item) => item.file === activeFile) || FILES[0]
  const externalRevision = state?.pdfEditor?.[selectedFile.slot]?.revision
  const editor = usePdfEditor(selectedFile.slot, serverHost, externalRevision, updatedBy)
  const mtime = state?.media?.pdfs?.[selectedFile.slot]?.mtime
  const activeUrl = useMemo(() => {
    const base = pdfUrl(selectedFile.file, serverHost)
    return mtime ? `${base}?v=${mtime}` : base
  }, [mtime, selectedFile.file, serverHost])

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
            onClick={() => setActiveFile(item.file)}>
            {item.label}
          </button>
        ))}
        <span>Общий редактор документов</span>
        <button onClick={close}>Закрыть</button>
      </div>
      <PdfEditorToolbar editor={editor} />
      <div className="pdf-library-editor__document">
        <PdfDocument key={activeFile} url={activeUrl} resetKey={activeFile}
          editor={{ pages: editor.doc.pages, editMode: editor.editMode, selected: editor.selected,
            assetOrigin: editor.assetOrigin, onSelect: editor.select, onChange: editor.update }} />
      </div>
    </div>
  )
}
