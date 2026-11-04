(function () {
  Neural.me().then((m) => Neural.mountNav(location.pathname, m));
  document.querySelectorAll("pre, code").forEach((p) => (p.textContent = p.textContent.split("{{BASE}}").join(location.origin)));
  document.querySelectorAll(".ctabs").forEach((tabs) => {
    const panes = tabs.parentElement.querySelectorAll(".cpane");
    tabs.querySelectorAll("button").forEach((b, i) => {
      b.onclick = () => {
        tabs.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
        panes.forEach((x) => x.classList.remove("on"));
        b.classList.add("on"); panes[i].classList.add("on");
      };
    });
    tabs.querySelector("button").click();
  });
})();
