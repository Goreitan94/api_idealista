// app.js
const axios = require('axios');

// --- CONFIGURACIÓN ---
const {
  AIRTABLE_BASE_ID,
  AIRTABLE_TABLE_ID,
  AIRTABLE_TOKEN,
  OUTLOOK_CLIENT_ID,
  OUTLOOK_CLIENT_SECRET,
  OUTLOOK_TENANT_ID,
  OUTLOOK_USER_EMAIL,
  SALES_MANAGEMENT_TABLE_ID
} = process.env;

const SENDER_FILTER = "reply@idealista.com";
const COMMERCIAL_EMAIL = "m.ortiz@apolore.es";
const TEST_EMAIL = "goreitan94@gmail.com"; // <-- Tu correo para pruebas

// --- FUNCIÓN PRINCIPAL ---
async function main() {
  console.log("Iniciando la ejecución del script...");

  try {
    const accessToken = await getMicrosoftGraphToken();
    if (!accessToken) {
      console.log("No se pudo obtener el token de acceso. Abortando.");
      return;
    }
    console.log("Token de acceso obtenido correctamente.");

    const emails = await getUnreadEmails(accessToken);
    if (emails.length === 0) {
      console.log("No se encontraron correos nuevos de Idealista.");
      return;
    }
    console.log(`Se encontraron ${emails.length} correos para procesar.`);

    for (const email of emails) {
      console.log(`Procesando correo con asunto: ${email.subject}`);

      const parsedData = parseEmail(email);
      console.log("Datos extraídos:", JSON.stringify(parsedData, null, 2));

      // Solo crear el registro si tenemos al menos un email o un teléfono válidos
      if (parsedData.email_cliente !== "-" || parsedData.telefono !== "-") {
        
        // Paso 1: Crear el registro inicial y obtener su ID
        const newRecordId = await createAirtableRecord(parsedData);
        console.log(`Registro principal creado con ID: ${newRecordId}`);
        
        // Paso 2: Vincular el registro con la tabla de Sales Management
        if (parsedData.referencia && parsedData.referencia !== "-") {
          const linkedRecordId = await findLinkedRecordId(parsedData.referencia);
          if (linkedRecordId) {
            await linkRecordsInAirtable(newRecordId, linkedRecordId);
            console.log(`Registro principal vinculado con Sales Management ID: ${linkedRecordId}`);
          } else {
            console.log("No se encontró un registro para vincular con la referencia.");
          }
        } else {
            console.log("El correo no tiene una referencia válida. Saltando la vinculación.");
        }
        
        // Paso 3: Enviar el correo al comercial con el enlace al nuevo registro
        await sendCommercialEmail(accessToken, newRecordId);

        // Paso 4: Enviar el correo de agradecimiento al cliente
        if (parsedData.email_cliente && parsedData.email_cliente !== "-") {
          await sendClientEmail(accessToken, parsedData);
        }

      } else {
        console.log("No se extrajo información de contacto válida. No se creará registro en Airtable.");
      }

      // Marcar el correo como leído para no procesarlo de nuevo
      await markEmailAsRead(accessToken, email.id);
      console.log(`Correo ${email.id} marcado como leído.`);
    }

  } catch (error) {
    console.error("Ocurrió un error en el flujo principal:", error.message);
    if (error.response) {
      console.error("Detalles del error:", JSON.stringify(error.response.data, null, 2));
    }
  }
}

// --- FUNCIONES DE MICROSOFT GRAPH (OUTLOOK) ---

async function getMicrosoftGraphToken() {
  const url = `https://login.microsoftonline.com/${OUTLOOK_TENANT_ID}/oauth2/v2.0/token`;
  const params = new URLSearchParams();
  params.append('client_id', OUTLOOK_CLIENT_ID);
  params.append('scope', 'https://graph.microsoft.com/.default');
  params.append('client_secret', OUTLOOK_CLIENT_SECRET);
  params.append('grant_type', 'client_credentials');

  const response = await axios.post(url, params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  });
  return response.data.access_token;
}

async function getUnreadEmails(token) {
  const url = `https://graph.microsoft.com/v1.0/users/${OUTLOOK_USER_EMAIL}/messages?$filter=isRead eq false and from/emailAddress/address eq '${SENDER_FILTER}'&$select=id,subject,body,from`;
  const response = await axios.get(url, { headers: { 'Authorization': `Bearer ${token}` }});
  return response.data.value;
}

async function markEmailAsRead(token, messageId) {
  const url = `https://graph.microsoft.com/v1.0/users/${OUTLOOK_USER_EMAIL}/messages/${messageId}`;
  await axios.patch(url, { isRead: true }, {
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
  });
}

async function sendCommercialEmail(token, airtableRecordId) {
  const recordUrl = `https://airtable.com/${AIRTABLE_BASE_ID}/${AIRTABLE_TABLE_ID}/${airtableRecordId}`;
  const url = `https://graph.microsoft.com/v1.0/users/${OUTLOOK_USER_EMAIL}/sendMail`;
  const emailContent = {
    message: {
      subject: "Nuevo Lead de Idealista",
      body: {
        contentType: "Html",
        content: `Se ha creado un nuevo registro en Airtable. <br><br> Haz clic aquí para ver todos los detalles: <a href="${recordUrl}">${recordUrl}</a>`
      },
      toRecipients: [{
        emailAddress: {
          address: COMMERCIAL_EMAIL
        }
      },
      {
        emailAddress: {
          address: TEST_EMAIL
        }
      }]
    }
  };
  await axios.post(url, emailContent, { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }});
  console.log(`Correo enviado a ${COMMERCIAL_EMAIL} y ${TEST_EMAIL} con el enlace al nuevo registro.`);
}

// --- FUNCIÓN ADICIONAL PARA CLIENTES ---
async function sendClientEmail(token, data) {
  const url = `https://graph.microsoft.com/v1.0/users/${OUTLOOK_USER_EMAIL}/sendMail`;
  const emailContent = {
    message: {
      subject: "Gracias por tu interés en la propiedad - UrbenEye",
      body: {
        contentType: "Html",
        content: `
          Hola ${data.nombre_cliente.split(' ')[0]},
          <br><br>
          Gracias por tu interés en la propiedad <a href="${data.enlace_inmueble}">${data.direccion_inmueble}</a>.
          <br><br>
          En breve, uno de nuestros comerciales se pondrá en contacto contigo para resolver cualquier duda.
          <br><br>
          Saludos,
          <br>
          Equipo UrbenEye
        `
      },
      toRecipients: [{
        emailAddress: {
          address: data.email_cliente
        }
      }]
    }
  };
  try {
    await axios.post(url, emailContent, { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }});
    console.log(`Correo de agradecimiento enviado a ${data.email_cliente}.`);
  } catch (error) {
    console.error(`Error al enviar correo al cliente ${data.email_cliente}:`, error.message);
  }
}

// --- FUNCIÓN DE PARSEO ---

function parseEmail(json) {
  let html = json["body"]["content"] || "";
  let subject = json["subject"] || "";
  let text = html.replace(/<[^>]*>/g, "\n").replace(/\n+/g, "\n").trim();
  let nombre = "", email = "", telefono = "-", referencia = "-", enlace = "-", mensaje = text;

  const potentialMatches = text.match(/[679][\d\s\.\-]{8,}/g);
  if (potentialMatches) {
    for (const potential of potentialMatches) {
      const cleanedNumber = potential.replace(/[\s\.\-]/g, '');
      if (cleanedNumber.length === 9) {
        telefono = cleanedNumber;
        break;
      }
    }
  }

  const matchEmail = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
  if (matchEmail) email = matchEmail[0];

  const matchNombre = subject.match(/Nuevo mensaje de (.+?) sobre/i);
  if (matchNombre) {
    nombre = matchNombre[1].trim();
  }

  const matchRef = subject.match(/ref\.?\s*interna\s*([^,]+)/i) || subject.match(/con ref: ([^,]+)/i);
  if (matchRef) referencia = matchRef[1].trim();

  const matchCodigo = text.match(/C[oó]digo del anuncio:\s*(\d+)/i);
  if (matchCodigo) {
    enlace = `https://www.idealista.com/inmueble/${matchCodigo[1]}`;
  }

  const matchDireccion = subject.match(/sobre tu inmueble, (.+)$/i);
  let direccion = matchDireccion ? matchDireccion[1].replace(/con ref: [^,]+,/, "").trim() : "-";

  return {
    nombre_cliente: nombre || "-",
    email_cliente: email || "-",
    telefono: telefono,
    referencia: referencia,
    enlace_inmueble: enlace,
    direccion_inmueble: direccion,
    mensaje: mensaje
  };
}

// --- FUNCIONES DE AIRTABLE ---

async function createAirtableRecord(data) {
  const url = `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${AIRTABLE_TABLE_ID}`;
  const payload = {
    records: [{
      fields: {
        "Lead Nane": data.nombre_cliente,
        "Email": data.email_cliente,
        "Telefono": data.telefono,
        "Mensaje Idealista": data.mensaje,
        "id test ": data.referencia
      }
    }]
  };
  const response = await axios.post(url, payload, {
    headers: { 'Authorization': `Bearer ${AIRTABLE_TOKEN}`, 'Content-Type': 'application/json' }
  });
  console.log(`Registro creado en Airtable para: ${data.nombre_cliente}`);
  return response.data.records[0].id;
}

async function findLinkedRecordId(referencia) {
  const url = `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${SALES_MANAGEMENT_TABLE_ID}?filterByFormula=({id test } = '${referencia}')`;
  try {
    const response = await axios.get(url, {
      headers: { 'Authorization': `Bearer ${AIRTABLE_TOKEN}` }
    });
    if (response.data.records.length > 0) {
      return response.data.records[0].id;
    }
    return null;
  } catch (error) {
    console.error("Error buscando registro en Sales Management:", error.message);
    return null;
  }
}

async function linkRecordsInAirtable(mainRecordId, linkedRecordId) {
  const url = `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${AIRTABLE_TABLE_ID}/${mainRecordId}`;
  const payload = {
    fields: {
      "Sales Management": [linkedRecordId]
    }
  };
  await axios.patch(url, payload, {
    headers: { 'Authorization': `Bearer ${AIRTABLE_TOKEN}`, 'Content-Type': 'application/json' }
  });
}

// --- INICIAR EJECUCIÓN ---
main();
