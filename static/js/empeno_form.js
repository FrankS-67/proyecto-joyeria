(() => {
  const articulos = document.querySelector("#articulos");
  if (!articulos) return;

  const tarifasPrestamo = JSON.parse(document.querySelector("#valores-oro").textContent);
  const contador = document.querySelector("#id_articulos-TOTAL_FORMS");
  const maximoForms = Number(
    document.querySelector("#id_articulos-MAX_NUM_FORMS").value
  );
  const totalCalculado = document.querySelector("#valor-calculado-total");
  const maximoPrestable = document.querySelector("#valor-maximo-prestable");
  const agregar = document.querySelector("#agregar-articulo");
  const campoPrestamo = document.querySelector('[name="valor_prestamo"]');
  const usarMaximo = document.querySelector("#usar-maximo-prestable");
  let maximoPrestableActual = 0n;

  const moneda = valor => new Intl.NumberFormat("es-CO", {
    maximumFractionDigits: 0,
  }).format(valor);

  const decimalEscalado = (valor, decimales) => {
    const partes = String(valor).split(".");
    const entero = partes[0];
    const fraccion = partes[1] || "";
    if (!/^\d+$/.test(entero) || fraccion.length > decimales || !/^\d*$/.test(fraccion)) {
      return 0n;
    }
    return BigInt(entero) * (10n ** BigInt(decimales))
      + BigInt((fraccion + "0".repeat(decimales)).slice(0, decimales) || "0");
  };

  const actualizarValorCalculado = () => {
    let valorEscalado = 0n;
    articulos.querySelectorAll(".articulo-form").forEach(fila => {
      if (fila.hidden) return;
      const tipo = fila.querySelector('[name$="-tipo_oro"]');
      const peso = fila.querySelector('[name$="-peso_gramos"]');
      if (tipo && peso && tipo.value && peso.value) {
        const tarifaCentavos = decimalEscalado(tarifasPrestamo[tipo.value] || 0, 2);
        const pesoCentesimas = decimalEscalado(peso.value, 2);
        valorEscalado += tarifaCentavos * pesoCentesimas;
      }
    });
    const valorRedondeado = (valorEscalado + 5000n) / 10000n;
    maximoPrestableActual = (valorEscalado / 10000000n) * 1000n;
    totalCalculado.textContent = `$ ${moneda(valorRedondeado)}`;
    maximoPrestable.textContent = `$ ${moneda(maximoPrestableActual)}`;
    if (campoPrestamo) {
      if (maximoPrestableActual > 0n) campoPrestamo.max = String(maximoPrestableActual);
      else campoPrestamo.removeAttribute("max");
    }
    if (usarMaximo) usarMaximo.disabled = maximoPrestableActual < 50000n;
  };

  const actualizarBotonAgregar = () => {
    agregar.disabled = maximoForms > 0 && Number(contador.value) >= maximoForms;
  };

  const enlazarFila = fila => {
    fila.querySelectorAll("select, input").forEach(campo => {
      campo.addEventListener("change", actualizarValorCalculado);
      campo.addEventListener("input", actualizarValorCalculado);
    });
    fila.querySelector(".quitar-articulo").addEventListener("click", () => {
      const eliminar = fila.querySelector('[name$="-DELETE"]');
      if (eliminar) {
        eliminar.checked = true;
        fila.hidden = true;
      }
      actualizarValorCalculado();
    });
  };

  articulos.querySelectorAll(".articulo-form").forEach(enlazarFila);
  if (usarMaximo) {
    usarMaximo.addEventListener("click", () => {
      campoPrestamo.value = String(maximoPrestableActual);
      campoPrestamo.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }
  agregar.addEventListener("click", () => {
    const indice = Number(contador.value);
    if (maximoForms > 0 && indice >= maximoForms) return;
    const plantilla = document.querySelector("#articulo-vacio").innerHTML;
    const contenido = plantilla.replaceAll("__prefix__", indice);
    articulos.insertAdjacentHTML("beforeend", contenido);
    contador.value = indice + 1;
    enlazarFila(articulos.lastElementChild);
    actualizarBotonAgregar();
    actualizarValorCalculado();
  });
  actualizarBotonAgregar();
  actualizarValorCalculado();
})();
