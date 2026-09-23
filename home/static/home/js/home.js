

//ENVIO DE PDF DO DOFMULARIO DE ENVIO DE IDEIA

const pdfInput = document.getElementById("idea-pdf");
const pdfButtonText = document.querySelector(".file-upload-text");
const pdfFileName = document.querySelector(".file-upload-name");
const pdfButton = document.querySelector(".file-upload-button");
const submitIdeaForm = document.querySelector(".submit-idea-form");
const githubInput = document.getElementById("idea-github");
const sourceError = document.querySelector(".form-source-error");

pdfInput.addEventListener("change", function () {
    const selectedFile = pdfInput.files[0];

    if (selectedFile) {
        sourceError.hidden = true;
    }

    if (!selectedFile) {
        pdfButtonText.textContent = "Selecionar PDF";
        pdfFileName.textContent = "Nenhum PDF selecionado";
        pdfButton.classList.remove("file-selected");
        pdfFileName.classList.remove("file-name-selected");
        return;
    }

    pdfButtonText.textContent = "Trocar PDF";
    pdfFileName.textContent = selectedFile.name;
    pdfButton.classList.add("file-selected");
    pdfFileName.classList.add("file-name-selected");
});

submitIdeaForm.addEventListener("submit", function (event) {
    const selectedPdf = pdfInput.files[0];
    const githubUrl = githubInput.value.trim();

    if (!selectedPdf && !githubUrl) {
        event.preventDefault();
        sourceError.hidden = false;
    } else {
        sourceError.hidden = true;
    }
});

githubInput.addEventListener("input", function () {
    const githubUrl = githubInput.value.trim();

    if (githubUrl) {
        sourceError.hidden = true;
    }
});

//FINAL DO ENVIO DE PDF DO DOFMULARIO DE ENVIO DE IDEIA