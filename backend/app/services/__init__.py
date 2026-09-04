"""Business logic that is not itself an HTTP endpoint.

The routers in ``app/routers/`` handle HTTP: reading the request, checking who
is logged in, choosing a status code. The real work lives here instead, so it
can be tested directly without going through a web request.

    ml_service.py        loads the Keras model and classifies an image
    image_service.py     saves and deletes published listing images
    category_service.py  normalises category names, prevents duplicates
    stats_service.py     average price per gram, and the best average
"""
