document.addEventListener("DOMContentLoaded", () => {
    cargarComboDocentes();
});

async function cargarComboDocentes() {
    const data = await traerDocentes();
    const datosJson = {};
    if (!data) return;

    const comboDocentes = document.getElementById("comboDocentes");
    
    // Si tu backend devuelve un array como data.docentes
    data.docentes.forEach(doc => {
        const option = document.createElement("option");
        option.value = doc.ID_EMPLEADO;   // value que usarás para backend
        option.textContent = doc.NOMBRE; // lo que ve el usuario
        comboDocentes.appendChild(option);
    });


    comboDocentes.addEventListener("change", async function() {
        const lblAviso = document.querySelector(".lblAviso");
        lblAviso.hidden = true;
      });
      
      
      const comboDocumento = document.getElementById("comboDocumento");
      
      const documento = await traerDocumentos();
      llenarComboDocumentos(documento);
    function llenarComboDocumentos(documentos){
        comboDocumento.innerHTML = ""; 
            const option = document.createElement("option");
            option.textContent = "Seleccione uno"; // lo que ve el usuario
            comboDocumento.appendChild(option);
        if (!documentos){
            const option = document.createElement("option");
            option.textContent = "Sin documentos"; // lo que ve el usuario
            comboDocumento.appendChild(option);
        }


        console.log(documentos);
        documentos.datos_json.forEach(doc => {
            const option = document.createElement("option");
            option.class = "optionDocumento";
            option.value = doc.ID_DOCUMENTO;   // value que usarás para backend
            option.textContent = doc.NOMBRE; // lo que ve el usuario
            comboDocumento.appendChild(option);
        });
    }

    const btnInsertar = document.getElementById("btnInsertar");
    btnInsertar.addEventListener("click", async () => {
        const lblAviso = document.querySelector(".lblAviso");
        lblAviso.hidden = true;
        mandarDocumento(datosJsonObj);
    });

    let datosJsonObj;

    comboDocumento.addEventListener("change", async function() {
        const idDocumentoSeleccionado = comboDocumento.value;
        const datosJsonResponse = await traerDatosJson(idDocumentoSeleccionado);
        const lblAviso = document.querySelector(".lblAviso");
        lblAviso.hidden = true;
        let datosJson = datosJsonResponse.datos_json;
        try {
            datosJsonObj = (typeof datosJson === "string") ? JSON.parse(datosJson) : datosJson;
            console.log(datosJsonObj);
            agregarVariables(datosJsonObj);
        } catch (err) {
            console.error("Error parseando datos_json:", err);
            return;
        }
    });


    function idDocentes(){
        let combo = document.getElementById("comboDocentes");
        let textoVisible = combo.options[combo.selectedIndex];
        console.log( textoVisible.value);
        return textoVisible.value;
    }
    function idDocumentos(){
        let combo = document.getElementById("comboDocumento");
        let textoVisible = combo.options[combo.selectedIndex];
        console.log( textoVisible.value);
        return textoVisible.value;
    }
    function mandarDocumento(datosJson){
        for (const key in datosJson) {
            if (datosJson.hasOwnProperty(key)) {
                const value = datosJson[key];
                console.log(`Clave: ${key}, Valor: ${value}`);
                const input = document.getElementById(key);
                if (input) {

                    datosJson[key] = input.value;
                } else {
                    console.warn(`No se encontró el input para la clave: ${key}`);
                }
            }
        }
        const idDocente = idDocentes();
        const idDocumento = idDocumentos();
        console.log("Datos a insertar:", datosJson);
        console.log("ID Docente:", idDocente);
        console.log("ID Documento:", idDocumento);
        insertar(idDocente, idDocumento, datosJson);
    }
}


function agregarVariables(datosJsonObj) {
    const formDatos = document.getElementById("formDatosJson");
    
    formDatos.innerHTML = "";
    const comboDocumento = document.getElementById("comboDocumento");
            const option = document.createElement("option");
            option.textContent = "Seleccione 1"; // lo que ve el usuario
            comboDocumento.appendChild(option);

    const comboDocentes = document.getElementById("comboDocentes"); 
        option.textContent = "Seleccione uno"; // lo que ve el usuario
        comboDocentes.appendChild(option);
    // Limpiar contenido previo
      for (const key in datosJsonObj) {
      if (datosJsonObj.hasOwnProperty(key)) {
          const div = document.createElement("div");
          div.className = "divDatosJson";
            const value = datosJsonObj[key];
            console.log(`Clave: ${key}, Valor: ${value}`);

            // Crear label
            const label = document.createElement("label");
            label.setAttribute("for", key);
            label.textContent = key + ":";

            // Crear input
            const input = document.createElement("input");
            input.type = "text";
            input.className = "inputDatosJson";
            input.id = key;
            input.value = value;
            div.appendChild(label);
            div.appendChild(input);
            formDatos.appendChild(div);


            // Salto de línea
            formDatos.appendChild(document.createElement("br"));
        }
    }
    
}



async function traerDocentes(){
      try{
    const response = await fetch("http://localhost:5000/traerIdDoce", {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();

    if (data.estatus) {
      console.log("Datos de cuenta:", data);
      return data;
    } else {
      console.log("Error:", data.error);
      return null;
    }
  } catch (error) {
    console.error("Error en traerDatosCuenta:", error);
    return null;
  }
}

async function traerDocumentos(){
    try{
    const response = await fetch("http://localhost:5000/traerDocumentoLlenado", {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();

    if (data.estatus) {
      console.log("Datos de cuenta:", data);
      return data;
    } else {
      console.log("Error:", data.error);
      return null;
    }
  } catch (error) {
    console.error("Error en traerDatosCuenta:", error);
    return null;
  }
}

async function insertar(idDocente,id_documento, datosJson){
        try{
            const lblAviso = document.querySelector(".lblAviso");
    const response = await fetch("http://localhost:5000/insertarDocumento", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idEmpleado: idDocente, idDocumento: id_documento, datosJson: datosJson })
    });
    const data = await response.json();

    if (data.estatus) {
        lblAviso.hidden = false;
        lblAviso.textContent = "Documento insertado correctamente.";
      console.log("Datos de cuenta:", data);
      return data;
    } else {
        lblAviso.hidden = false;
        lblAviso.textContent = "Error al insertar el documento.";
      console.log("Error:", data.error);
      return null;
    }
  } catch (error) {
    lblAviso.hidden = false;
    lblAviso.textContent = "Error al insertar el documento.";
    console.error("Error en traerDatosJson:", error);
    return null;
  }
}
async function traerDatosJson(id_documento){
        try{
    const response = await fetch("http://localhost:5000/traerDatosDocumento", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({  idDocumento: id_documento })
    });
    const data = await response.json();

    if (data.estatus) {
      console.log("Datos de cuenta:", data);
      return data;
    } else {
      console.log("Error:", data.error);
      return null;
    }
  } catch (error) {
    console.error("Error en traerDatosJson:", error);
    return null;
  }
}

