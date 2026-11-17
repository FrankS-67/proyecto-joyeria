(() => {
  const detalles = document.querySelector("#detalles-venta");
  if (!detalles) return;

  const contador = document.querySelector("#id_detalles-TOTAL_FORMS");
  const enlazarDetalle = detalle => {
    detalle.querySelector(".quitar-detalle").addEventListener("click", () => {
      if (detalles.querySelectorAll(".detalle-venta").length <= 1) {
        detalle.querySelectorAll("select, input").forEach(campo => {
          if (campo.tagName === "SELECT") campo.selectedIndex = 0;
          else campo.value = "";
        });
        return;
      }
      detalle.remove();
      actualizarIndices();
    });
  };

  const actualizarIndices = () => {
    detalles.querySelectorAll(".detalle-venta").forEach((fila, indice) => {
      fila.querySelectorAll("[name], [id], label[for]").forEach(elemento => {
        ["name", "id", "for"].forEach(atributo => {
          const valor = elemento.getAttribute(atributo);
          if (valor) {
            elemento.setAttribute(
              atributo,
              valor.replace(/detalles-\d+-/, `detalles-${indice}-`)
            );
          }
        });
      });
    });
    contador.value = detalles.querySelectorAll(".detalle-venta").length;
  };

  detalles.querySelectorAll(".detalle-venta").forEach(enlazarDetalle);
  document.querySelector("#agregar-detalle").addEventListener("click", () => {
    const indice = Number(contador.value);
    const html = document.querySelector("#detalle-vacio").innerHTML
      .replaceAll("__prefix__", indice);
    detalles.insertAdjacentHTML("beforeend", html);
    enlazarDetalle(detalles.lastElementChild);
    contador.value = indice + 1;
  });
})();
