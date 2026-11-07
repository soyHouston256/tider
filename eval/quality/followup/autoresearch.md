# Prueba pareada de recuperación y diagnóstico

Congelación previa a los cambios, 6 de noviembre de 2026. La base es la versión local usada en la corrida v1. Se mantienen el corpus, el modelo, el presupuesto y la rúbrica. El conjunto anterior es de desarrollo. Las nuevas preguntas y ventanas son variantes internas reservadas para una sola comparación. Una persona distinta aún debe validar las etiquetas.

Para el buscador, la medida principal es Hit@4 en preguntas respondibles. Debe mejorar y conservar al menos el número de abstenciones correctas de la base en preguntas sin respuesta. La posición del primer pasaje se informa por separado. Se conservarán ambos rankings.

Para el investigador, se registra ubicación, mecanismo, acierto conjunto con todas las citas y falsas atribuciones en controles. La prioridad es subir el acierto conjunto sin aumentar las atribuciones en controles. Una investigación por versión y ventana, sin reintentos de casos. Es una prueba pequeña y exploratoria, con intervalos de Wilson y comparaciones pareadas. El piloto de GKE queda fuera de esta prueba.
