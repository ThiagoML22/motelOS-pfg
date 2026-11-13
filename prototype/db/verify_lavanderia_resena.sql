-- Verifica la migracion 018 con el rol de la aplicacion, motel_app: con lavanderia propia no se anota ropa que vaya o
-- vuelva de una lavanderia de afuera, el motivo «Otro» lleva su detalle (y solo el) y la resena del cliente es corta.
-- Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_lavanderia_resena.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    conserje integer;
    guardia integer;
    categoria integer;
    tarifa integer;
    habitacion integer;
    habitacion_dos integer;
    turno uuid;
    turno_dos uuid;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.l', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif resena') RETURNING id INTO categoria;
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
    VALUES ('Verif resena', 8000, 120, 0, 30, 2500, true, categoria) RETURNING id INTO tarifa;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9941, 'Ocupada', categoria) RETURNING id INTO habitacion;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9942, 'Ocupada', categoria) RETURNING id INTO habitacion_dos;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (gen_random_uuid(), habitacion, tarifa, 'Auto', now(), 'En Curso', 8000, 8000, conserje, guardia)
    RETURNING id INTO turno;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (gen_random_uuid(), habitacion_dos, tarifa, 'Auto', now(), 'En Curso', 8000, 8000, conserje, guardia)
    RETURNING id INTO turno_dos;
    UPDATE establecimientos SET lavanderia_propia = true WHERE id = 1;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Con lavanderia propia: compras y bajas si, idas y vueltas de la lavanderia no.
    INSERT INTO ropa_movimientos (guardia_id, operador_id, prenda, tipo, cantidad) VALUES (guardia, conserje, 'TOALLAS', 'COMPRA', 12);
    INSERT INTO ropa_movimientos (guardia_id, operador_id, prenda, tipo, cantidad) VALUES (guardia, conserje, 'TOALLAS', 'BAJA', 1);
    bloqueado := false;
    BEGIN INSERT INTO ropa_movimientos (guardia_id, operador_id, prenda, tipo, cantidad)
    VALUES (guardia, conserje, 'SABANAS', 'LAVANDERIA_SALE', 10);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Salio ropa a una lavanderia de afuera donde se lava en el motel'; END IF;

    -- 2. La gerencia pasa a una lavanderia de afuera: ahora si, y lo ya anotado queda.
    UPDATE establecimientos SET lavanderia_propia = false WHERE id = 1;
    INSERT INTO ropa_movimientos (guardia_id, operador_id, prenda, tipo, cantidad)
    VALUES (guardia, conserje, 'SABANAS', 'LAVANDERIA_SALE', 10);
    SELECT count(*) INTO filas FROM ropa_movimientos WHERE guardia_id = guardia;
    IF filas <> 3 THEN RAISE EXCEPTION 'Los movimientos de la guardia no son tres: %', filas; END IF;

    -- 3. «Otro» con su detalle entra; sin detalle, o un detalle en otro motivo, no.
    INSERT INTO clientes_perdidos (motivo, detalle, operador_id, guardia_id) VALUES ('OTRO', 'Venia con mascota', conserje, guardia);
    INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('SIN_LUGAR', conserje, guardia);
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('OTRO', conserje, guardia);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un «Otro» sin detalle'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, detalle, operador_id, guardia_id) VALUES ('OTRO', '   ', conserje, guardia);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un «Otro» con el detalle en blanco'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, detalle, operador_id, guardia_id) VALUES ('PRECIO', 'Caro', conserje, guardia);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un detalle en un motivo que no es «Otro»'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('NINGUNO', conserje, guardia);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un motivo desconocido'; END IF;

    -- 4. La resena: seis palabras entran, siete no; tampoco en blanco ni en varias lineas.
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje, resena)
    VALUES (turno, habitacion, 4, 'uno dos tres cuatro cinco seis siete');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una resena de siete palabras'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje, resena) VALUES (turno, habitacion, 4, '  ');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una resena en blanco'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje, resena) VALUES (turno, habitacion, 4, E'Muy\nbien');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una resena en dos lineas'; END IF;
    INSERT INTO calificaciones (turno_id, habitacion_id, puntaje, problemas, resena)
    VALUES (turno, habitacion, 4, 2, 'Muy lindo, algo de ruido nomas');
    INSERT INTO calificaciones (turno_id, habitacion_id, puntaje) VALUES (turno_dos, habitacion_dos, 5);
    SELECT count(*) INTO filas FROM calificaciones WHERE resena IS NOT NULL AND turno_id IN (turno, turno_dos);
    IF filas <> 1 THEN RAISE EXCEPTION 'Las resenas guardadas no son una: %', filas; END IF;

    RAISE NOTICE 'verify_lavanderia_resena: lavanderia propia o de afuera, motivo «Otro» con detalle y resena corta verificados';
END $$;
ROLLBACK;
