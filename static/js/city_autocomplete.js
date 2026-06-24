(function () {
  var citiesData = null;
  var loadPromise = null;

  function loadCities(baseUrl) {
    if (loadPromise) return loadPromise;
    var url = (baseUrl || '') + '/static/cities.json';
    loadPromise = fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) { citiesData = data; return data; });
    return loadPromise;
  }

  function attachAutocomplete(input, baseUrl) {
    var listId = 'city-ac-list';
    var datalist = document.getElementById(listId);
    if (!datalist) {
      datalist = document.createElement('datalist');
      datalist.id = listId;
      document.body.appendChild(datalist);
    }
    input.setAttribute('list', listId);
    input.setAttribute('autocomplete', 'off');

    input.addEventListener('focus', function () {
      loadCities(baseUrl);
    }, { once: true });

    input.addEventListener('input', function () {
      if (!citiesData) return;
      var q = this.value.toLowerCase().trim();
      if (q.length < 2) { datalist.innerHTML = ''; return; }

      var options = [];
      for (var i = 0; i < citiesData.length && options.length < 60; i++) {
        var city = citiesData[i];
        var enLower = city.en.toLowerCase();
        var ruLower = city.ru ? city.ru.toLowerCase() : '';
        if (enLower.indexOf(q) === 0 || ruLower.indexOf(q) === 0) {
          options.push('<option value="' + city.en.replace(/"/g, '&quot;') + '">' +
            (city.ru ? city.ru + ' / ' + city.en : city.en) + '</option>');
        }
      }
      // Second pass: contains (but not starts-with) matches
      if (options.length < 20) {
        for (var i = 0; i < citiesData.length && options.length < 60; i++) {
          var city = citiesData[i];
          var enLower = city.en.toLowerCase();
          var ruLower = city.ru ? city.ru.toLowerCase() : '';
          if (enLower.indexOf(q) > 0 || ruLower.indexOf(q) > 0) {
            options.push('<option value="' + city.en.replace(/"/g, '&quot;') + '">' +
              (city.ru ? city.ru + ' / ' + city.en : city.en) + '</option>');
          }
        }
      }
      datalist.innerHTML = options.join('');
    });
  }

  function init(baseUrl) {
    document.querySelectorAll('[data-city-input]').forEach(function (el) {
      attachAutocomplete(el, baseUrl);
    });
  }

  window.CityAutocomplete = { init: init, attach: attachAutocomplete };
})();
