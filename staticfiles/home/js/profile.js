document.querySelectorAll('.idea-remove-form').forEach(form => {
    form.addEventListener('submit', event => {
        if (!window.confirm('Excluir esta ideia? Esta ação não pode ser desfeita.')) event.preventDefault();
    });
});
