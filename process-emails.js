const axios = require('axios');

// --- CONFIGURACIÓN ---
const {
  AIRTABLE_BASE_ID,
  AIRTABLE_TABLE_ID,
  AIRTABLE_TOKEN,
  OUTLOOK_CLIENT_ID,
  OUTLOOK_CLIENT_SECRET,
  OUTLOOK_TENANT_ID,
  OUTLOOK_USER_EMAIL
} = process.env;

const SENDER_FILTER = "reply@idealista.com";

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
        await createAirtableRecord(parsedData);
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

// --- FUNCIÓN DE PARSEO (VERSIÓN CORREGIDA Y MEJORADA) ---

function parseEmail(json) {
  let html = json["body"]["content"] || "";
  let subject = json["subject"] || "";
  let text = html.replace(/<[^>]*>/g, "\n").replace(/\n+/g, "\n").trim();
  let nombre = "", email = "", telefono = "", referencia = "", enlace = "", mensaje = text;

  // --- MEJORA CRÍTICA: Búsqueda de teléfono mucho más específica ---
  // Busca un número español de 9 dígitos (que empiece por 6, 7 o 9), con o sin espacios.
  const matchTel = text.match(/(?:(?:\+|00)34[\s]?)?([679]\d{2}[\s]?\d{3}[\s]?\d{3})\b/);
  if (matchTel) {
    telefono = matchTel[1].replace(/\s/g, ''); // Cogemos el grupo capturado y quitamos espacios
  }

  const matchEmail = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}/);
  if (matchEmail) email = matchEmail[0];

  // La extracción del nombre desde el asunto es la más fiable
  const matchNombre = subject.match(/Nuevo mensaje de (.+?) sobre/i);
  if(matchNombre) {
      nombre = matchNombre[1].trim();
  }

  const matchRef = subject.match(/ref\.?\s*interna\s*([^,]+)/i) || subject.match(/con ref: ([^,]+)/i);
  if (matchRef) referencia = matchRef[1].trim();

  const matchCodigo = text.match(/C[oó]digo del anuncio:\s*(\d+)/i);
  if (matchCodigo) {
    enlace = `https://www.idealista.com/inmble/${matchCodigo[1]}`;
  }

  const matchDireccion = subject.match(/sobre tu inmueble, (.+)$/i);
  let direccion = matchDireccion ? matchDireccion[1].replace(/con ref: [^,]+,/, "").trim() : "";

  return {
    nombre_cliente: nombre || "-",
    email_cliente: email || "-",
    telefono: telefono || "-",
    referencia: referencia || "-",
    enlace_inmueble: enlace || "-",
    direccion_inmueble: direccion || "-",
    mensaje: mensaje
  };
}

// --- FUNCIÓN DE AIRTABLE ---
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
  await axios.post(url, payload, {
    headers: { 'Authorization': `Bearer ${AIRTABLE_TOKEN}`, 'Content-Type': 'application/json' }
  });
  console.log(`Registro creado en Airtable para: ${data.nombre_cliente}`);
}

// --- INICIAR EJECUCIÓN ---
main();
