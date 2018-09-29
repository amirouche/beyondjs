# beyondjs

beyondjs is a **prototype** framework that use a small client side
JavaScript kernel to render the html
via [snabbdom](https://github.com/snabbdom/snabbdom/) a virtual dom
library and forward DOM events to the backend via WebSockets. From
there the backend will process the event and return a JSON string
representing the new state of the DOM that will be interpreted by the
javascript runtime and rendered efficently.

Simply said, the developer doesn't need to write JavaScript, but needs
to learn DOM API. Even if, it's possible to use existing JavaScript
libraries it's not demonstrated.

Right now, there is a small "counter" application and a todomvc.

```shell
git clone https://github.com/amirouche/beyondjs
cd beyondjs
pipenv install --dev
pipenv shell
cd src
python3 main.py
```

Then goto [localhost:8080](http://localhost:8080/).

## TODO

- Support setting styles from Python
- Support redirect
- Support upload
- Support setting the title of the page
