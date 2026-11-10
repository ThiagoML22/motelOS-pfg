-- Verifica la migracion 014 con el rol de la aplicacion, motel_app: dos franjas activas de una categoria no se pisan
-- (tampoco cruzando la medianoche ni del domingo al lunes), la tarifa de una franja es de su misma categoria, hay una sola
-- vigente por franja, una franja no se borra y cada establecimiento ve solo las suyas. Corre en una transaccion que se
-- revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_franjas.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    categoria integer;
    categoria_dos integer;
    noche integer;
    domingo integer;
    filas integer;
    bloqueado boolean;
    minutos integer[];
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-fra', 'Otro') RETURNING id INTO otro;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif franja') RETURNING id INTO categoria;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif franja 2') RETURNING id INTO categoria_dos;
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
    VALUES ('Verif general', 8000, 120, 0, 30, 2500, true, categoria);

    SET LOCAL ROLE motel_app;

    -- 1. Viernes y sabado de 20 a 6 (16 + 32).
    INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Noche', 48, '20:00', '06:00')
    RETURNING id INTO noche;

    -- 2. El viernes a la noche sigue el sabado a las 2: una franja del sabado de madrugada se pisa.
    bloqueado := false;
    BEGIN INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Madrugada', 32, '01:00', '03:00');
    EXCEPTION WHEN exclusion_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se pisaron dos franjas en la madrugada del sabado'; END IF;

    -- 3. Justo donde termina la otra no se pisa: el sabado de 6 a 20 entra.
    INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Sabado de dia', 32, '06:00', '20:00');

    -- 4. Del domingo al lunes da la vuelta a la semana.
    INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Domingo noche', 64, '22:00', '05:00')
    RETURNING id INTO domingo;
    bloqueado := false;
    BEGIN INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Lunes temprano', 1, '04:00', '08:00');
    EXCEPTION WHEN exclusion_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se piso el lunes temprano con la noche del domingo'; END IF;

    -- 5. Otra categoria no molesta, y una franja dada de baja deja el lugar libre.
    INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria_dos, 'Noche', 48, '20:00', '06:00');
    UPDATE franjas_tarifa SET activa = false WHERE id = domingo;
    INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Lunes temprano', 1, '04:00', '08:00');

    -- 6. Mover una franja sobre otra tambien se rechaza.
    bloqueado := false;
    BEGIN UPDATE franjas_tarifa SET hasta = '07:00' WHERE id = noche;
    EXCEPTION WHEN exclusion_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se movio una franja sobre otra'; END IF;

    -- 7. El nombre es unico entre las activas de la categoria, sin importar mayusculas.
    bloqueado := false;
    BEGIN INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'NOCHE', 1, '12:00', '13:00');
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entraron dos franjas con el mismo nombre'; END IF;

    -- 8. Dias fuera de la mascara no entran.
    bloqueado := false;
    BEGIN INSERT INTO franjas_tarifa (categoria_id, nombre, dias, desde, hasta) VALUES (categoria, 'Nunca', 0, '12:00', '13:00');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una franja sin dias'; END IF;

    -- 9. La tarifa de la franja es de su categoria, y hay una sola vigente por franja.
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id, franja_id)
    VALUES ('Verif noche', 12000, 120, 0, 30, 3000, true, categoria, noche);
    bloqueado := false;
    BEGIN
        INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id, franja_id)
        VALUES ('Verif ajena', 12000, 120, 0, 30, 3000, false, categoria_dos, noche);
    EXCEPTION WHEN foreign_key_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una tarifa de otra categoria en la franja'; END IF;
    bloqueado := false;
    BEGIN
        INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id, franja_id)
        VALUES ('Verif doble', 13000, 120, 0, 30, 3000, true, categoria, noche);
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Quedaron dos tarifas vigentes en una franja'; END IF;

    -- 10. La tarifa de una franja no cuenta como la general: sigue habiendo una sola general vigente.
    bloqueado := false;
    BEGIN
        INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
        VALUES ('Verif general 2', 9000, 120, 0, 30, 2500, true, categoria);
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Quedaron dos tarifas generales vigentes'; END IF;

    -- 11. Una franja no se borra.
    bloqueado := false;
    BEGIN DELETE FROM franjas_tarifa WHERE id = noche;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro una franja'; END IF;

    -- 12. Otro establecimiento no ve las franjas del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM franjas_tarifa;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio las franjas de otro'; END IF;
    RAISE NOTICE 'verify_franjas: sin superposicion, misma categoria, una vigente por franja, sin borrado y aislamiento verificados';
END $$;
ROLLBACK;
