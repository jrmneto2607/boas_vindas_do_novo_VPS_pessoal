(() => {
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', event => {
            if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        });
    });
    document.querySelectorAll('[data-copy-link]').forEach(button => {
        button.addEventListener('click', async () => {
            const url = new URL(button.dataset.copyLink, window.location.origin).href;
            try {
                await navigator.clipboard.writeText(url);
                const iconButton = button.classList.contains('forum-icon-button');
                const original = button.textContent;
                const originalTitle = button.title;
                const originalLabel = button.getAttribute('aria-label');
                if (!iconButton) button.textContent = 'Link copiado!';
                button.title = 'Link copiado!';
                button.setAttribute('aria-label', 'Link copiado!');
                button.classList.add('is-copied');
                let notice = document.getElementById('forum-copy-notice');
                if (!notice) {
                    notice = document.createElement('span');
                    notice.id = 'forum-copy-notice';
                    notice.className = 'forum-visually-hidden';
                    notice.setAttribute('role', 'status');
                    document.body.append(notice);
                }
                notice.textContent = 'Link copiado!';
                clearTimeout(button.copyFeedbackTimer);
                button.copyFeedbackTimer = setTimeout(() => {
                    if (!iconButton) button.textContent = original;
                    button.title = originalTitle;
                    if (originalLabel) button.setAttribute('aria-label', originalLabel);
                    else button.removeAttribute('aria-label');
                    button.classList.remove('is-copied');
                    notice.textContent = '';
                }, 2500);
            } catch {
                window.prompt('Copie este link:', url);
            }
        });
    });
})();
