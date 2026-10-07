(() => {
    const textarea = document.querySelector('textarea[data-forum-editor]');
    if (!textarea || !window.Quill) return;

    const form = textarea.closest('form');
    const wrapper = document.createElement('div');
    wrapper.className = 'forum-editor';
    const toolbar = document.createElement('div');
    toolbar.setAttribute('role', 'group');
    toolbar.setAttribute('aria-label', 'Formatação da mensagem');
    toolbar.innerHTML = `
        <span class="ql-formats">
            <button type="button" class="ql-bold" aria-label="Negrito" title="Negrito"></button>
            <button type="button" class="ql-italic" aria-label="Itálico" title="Itálico"></button>
            <button type="button" class="ql-underline" aria-label="Sublinhado" title="Sublinhado"></button>
            <button type="button" class="ql-strike" aria-label="Riscado" title="Riscado"></button>
        </span>
        <span class="ql-formats">
            <select class="ql-color" aria-label="Cor do texto" title="Cor do texto">
                <option value="" selected>Cor padrão</option>
                <option value="#5eead4">Verde-água</option>
                <option value="#60a5fa">Azul</option>
                <option value="#fbbf24">Amarelo</option>
                <option value="#fb7185">Rosa</option>
                <option value="#c4b5fd">Lilás</option>
                <option value="#ffffff">Branco</option>
            </select>
        </span>
        <span class="ql-formats">
            <button type="button" class="ql-list" value="ordered" aria-label="Lista numerada" title="Lista numerada"></button>
            <button type="button" class="ql-list" value="bullet" aria-label="Lista com marcadores" title="Lista com marcadores"></button>
            <button type="button" class="ql-blockquote" aria-label="Citação" title="Citação"></button>
            <button type="button" class="ql-link" aria-label="Inserir link" title="Inserir link"></button>
        </span>
        <span class="ql-formats">
            <button type="button" class="ql-clean" aria-label="Limpar formatação" title="Limpar formatação"></button>
            <button type="button" class="ql-undo" aria-label="Desfazer" title="Desfazer">↶</button>
            <button type="button" class="ql-redo" aria-label="Refazer" title="Refazer">↷</button>
        </span>`;
    const host = document.createElement('div');
    wrapper.append(toolbar, host);
    textarea.before(wrapper);

    let quill;
    try {
        quill = new Quill(host, {
            theme: 'snow',
            bounds: wrapper,
            placeholder: textarea.getAttribute('placeholder'),
            formats: ['bold', 'italic', 'underline', 'strike', 'color', 'list', 'link', 'blockquote'],
            modules: {
                toolbar: {
                    container: toolbar,
                    handlers: {
                        undo() { this.quill.history.undo(); },
                        redo() { this.quill.history.redo(); },
                    },
                },
                history: { userOnly: true },
            },
        });
        const seed = document.getElementById('forum-editor-initial');
        if (seed) {
            const html = JSON.parse(seed.textContent);
            quill.setContents(quill.clipboard.convert({ html }), 'silent');
        }
        quill.history.clear();
    } catch (error) {
        wrapper.remove();
        return;
    }

    const label = form.querySelector(`label[for="${textarea.id}"]`);
    if (label) {
        label.id = `${textarea.id}_label`;
        label.removeAttribute('for');
        label.addEventListener('click', () => quill.focus());
        quill.root.setAttribute('aria-labelledby', label.id);
    }
    quill.root.setAttribute('role', 'textbox');
    quill.root.setAttribute('aria-multiline', 'true');
    quill.root.setAttribute('aria-required', 'true');
    if (textarea.getAttribute('aria-describedby')) {
        quill.root.setAttribute('aria-describedby', textarea.getAttribute('aria-describedby'));
    }
    if (textarea.getAttribute('aria-invalid')) {
        quill.root.setAttribute('aria-invalid', textarea.getAttribute('aria-invalid'));
    }
    const colorLabel = toolbar.querySelector('.ql-color-picker .ql-picker-label');
    if (colorLabel) {
        colorLabel.setAttribute('aria-label', 'Cor do texto');
        colorLabel.title = 'Cor do texto';
        const colorNames = {
            '': 'Cor padrão', '#5eead4': 'Verde-água', '#60a5fa': 'Azul',
            '#fbbf24': 'Amarelo', '#fb7185': 'Rosa', '#c4b5fd': 'Lilás', '#ffffff': 'Branco',
        };
        toolbar.querySelectorAll('.ql-picker-item').forEach(item => {
            const name = colorNames[item.dataset.value || ''] || 'Cor do texto';
            item.setAttribute('aria-label', name);
            item.title = name;
        });
    }
    const linkInput = wrapper.querySelector('.ql-tooltip input');
    if (linkInput) {
        linkInput.setAttribute('aria-label', 'Endereço do link');
        linkInput.setAttribute('data-link', 'https://exemplo.com');
    }

    wrapper.querySelectorAll('.ql-tooltip .ql-action, .ql-tooltip .ql-remove').forEach(button => {
        button.tabIndex = 0;
        button.setAttribute('role', 'button');
        button.setAttribute('aria-label', button.classList.contains('ql-remove') ? 'Remover link' : 'Editar ou salvar link');
        button.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                button.click();
            }
        });
    });

    const capacity = document.createElement('span');
    capacity.className = 'forum-editor-capacity';
    capacity.setAttribute('role', 'img');
    wrapper.append(capacity);

    const error = document.createElement('p');
    error.className = 'form-source-error';
    error.id = `${textarea.id}_editor_error`;
    error.setAttribute('role', 'alert');
    error.hidden = true;
    wrapper.after(error);
    textarea.required = false;
    textarea.hidden = true;
    textarea.classList.add('forum-editor-source');
    const maxLength = textarea.maxLength;
    const descriptions = textarea.getAttribute('aria-describedby') || '';
    quill.root.setAttribute('aria-describedby', `${descriptions} ${error.id}`.trim());

    function showError(message) {
        error.textContent = message;
        error.hidden = !message;
        if (message) {
            quill.root.setAttribute('aria-invalid', 'true');
        } else {
            quill.root.removeAttribute('aria-invalid');
        }
    }

    function sync() {
        const text = quill.getText().replace(/[\u200b\ufeff]/g, '').trim();
        textarea.value = text ? quill.getSemanticHTML() : '';
        const tooLong = maxLength > 0 && textarea.value.length > maxLength;
        const ratio = maxLength > 0 ? Math.min(textarea.value.length / maxLength, 1) : 0;
        const hue = ratio <= 0.7
            ? 145 - (ratio / 0.7) * 85
            : 60 * (1 - ratio) / 0.3;
        capacity.style.setProperty('--capacity-hue', hue.toFixed(1));
        const capacityLabel = tooLong
            ? 'A mensagem excedeu o limite permitido.'
            : ratio >= 0.9
                ? 'A mensagem está muito próxima do limite.'
                : ratio >= 0.65
                    ? 'A mensagem está se aproximando do limite.'
                    : 'A mensagem está dentro do limite.';
        capacity.title = capacityLabel;
        capacity.setAttribute('aria-label', capacityLabel);
        showError(tooLong
            ? 'A mensagem ultrapassou o limite permitido. Reduza o texto ou a formatação.'
            : '');
        return tooLong;
    }
    quill.on('text-change', sync);
    sync();
    form.addEventListener('submit', event => {
        const tooLong = sync();
        if (!textarea.value || tooLong) {
            event.preventDefault();
            if (!textarea.value) showError('Escreva uma mensagem antes de enviar.');
            quill.focus();
        }
    });
})();
