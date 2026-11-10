-- Verifica la migracion 008 con el rol de la aplicacion, motel_app: categorias de habitacion con una tarifa vigente
-- cada una, bajas y asignaciones, aislamiento, y las funciones de clave del perfil. Falla con error si alguna
-- garantia no se cumple. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_categorias_perfil.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    cat_otra integer;
    simple integer;
    vip integer;
    hab integer;
    gerencia_id integer;
    conserje_id integer;
    conserje_otro integer;
    hash_gerencia text;
    hash_conserje text;
    bloqueado boolean;
BEGIN
    -- Datos del dueno: otro establecimiento con su categoria y su conserje; usuarios del establecimiento 1.
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-cat', 'Otro') RETURNING id INTO otro;
    INSERT INTO categorias_habitacion (establecimiento_id, nombre) VALUES (otro, 'Simple') RETURNING id INTO cat_otra;
    INSERT INTO operadores (establecimiento_id, usuario, nombre_visible, hash_clave)
    VALUES (otro, 'verif.c', 'Conserje del otro', 'x') RETURNING id INTO conserje_otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.g', 'Gerencia', 'hash-g', 'ADMINISTRADOR') RETURNING id INTO gerencia_id;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave) VALUES ('verif.c', 'Conserje', 'hash-c')
    RETURNING id INTO conserje_id;
    SELECT id INTO simple FROM categorias_habitacion WHERE establecimiento_id = 1 ORDER BY id LIMIT 1;

    -- Claves compuestas: una habitacion del establecimiento 1 no usa una categoria de otro (ni siquiera el dueno).
    bloqueado := false;
    BEGIN INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (998, 'Libre', cat_otra);
    EXCEPTION WHEN foreign_key_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Una habitacion uso la categoria de otro establecimiento'; END IF;

    SET LOCAL ROLE motel_app;

    -- 1. Alta de una categoria con su tarifa; una vigente por categoria.
    INSERT INTO categorias_habitacion (nombre, color) VALUES ('VIP', '#7c3aed') RETURNING id INTO vip;
    INSERT INTO tarifas (nombre, tarifa_base, tarifa_fraccion, categoria_id, tope) VALUES ('VIP 1', 15000, 5000, vip, 30000);
    bloqueado := false;
    BEGIN INSERT INTO tarifas (nombre, tarifa_base, tarifa_fraccion, categoria_id) VALUES ('VIP 2', 1, 1, vip);
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Quedaron dos tarifas vigentes en una categoria'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO tarifas (nombre, tarifa_base, tarifa_fraccion, categoria_id, vigente, tope)
          VALUES ('VIP 3', 15000, 5000, vip, false, 100);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se acepto un tope menor que la estadia base'; END IF;

    -- 2. Una categoria con habitaciones activas no se da de baja; a una dada de baja no se asignan habitaciones.
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (997, 'Libre', vip) RETURNING id INTO hab;
    bloqueado := false;
    BEGIN UPDATE categorias_habitacion SET activa = false WHERE id = vip;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se dio de baja una categoria con habitaciones activas'; END IF;
    UPDATE habitaciones SET categoria_id = simple WHERE id = hab;
    UPDATE categorias_habitacion SET activa = false WHERE id = vip;
    bloqueado := false;
    BEGIN UPDATE habitaciones SET categoria_id = vip WHERE id = hab;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se asigno una habitacion a una categoria dada de baja'; END IF;

    -- 3. Aislamiento: las categorias de otro establecimiento no se ven ni se tocan.
    IF EXISTS (SELECT 1 FROM categorias_habitacion WHERE id = cat_otra) THEN
        RAISE EXCEPTION 'RLS: el establecimiento 1 vio una categoria de otro';
    END IF;
    bloqueado := false;
    BEGIN INSERT INTO categorias_habitacion (establecimiento_id, nombre) VALUES (otro, 'Pirata');
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'RLS: el establecimiento 1 creo una categoria en otro'; END IF;

    -- 4. Perfil: la aplicacion no escribe hash_clave directamente; si el nombre visible.
    UPDATE operadores SET nombre_visible = 'Conserje (nuevo nombre)' WHERE id = conserje_id;
    bloqueado := false;
    BEGIN UPDATE operadores SET hash_clave = 'robada' WHERE id = gerencia_id;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app escribio una clave directamente'; END IF;

    -- 5. La clave propia cambia solo la del usuario de la sesion.
    bloqueado := false;
    BEGIN PERFORM cambiar_clave_propia('sin-sesion');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio una clave sin usuario en la sesion'; END IF;
    PERFORM set_config('app.operador_id', conserje_id::text, true);
    PERFORM cambiar_clave_propia('hash-c-nuevo');
    IF (SELECT hash_clave FROM operadores WHERE id = conserje_id) <> 'hash-c-nuevo'
       OR (SELECT hash_clave FROM operadores WHERE id = gerencia_id) <> 'hash-g' THEN
        RAISE EXCEPTION 'La clave propia no cambio solo la del usuario de la sesion';
    END IF;

    -- 6. Restablecer: solo la gerencia, solo a un conserje de su establecimiento.
    bloqueado := false;
    BEGIN PERFORM restablecer_clave_conserje(conserje_id, 'x');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un conserje restablecio una clave'; END IF;
    PERFORM set_config('app.operador_id', gerencia_id::text, true);
    bloqueado := false;
    BEGIN PERFORM restablecer_clave_conserje(gerencia_id, 'x');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se restablecio la clave de la gerencia'; END IF;
    bloqueado := false;
    BEGIN PERFORM restablecer_clave_conserje(conserje_otro, 'x');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se restablecio la clave de un conserje de otro establecimiento'; END IF;
    PERFORM restablecer_clave_conserje(conserje_id, 'hash-c-restablecido');

    RESET ROLE;
    SELECT hash_clave INTO hash_gerencia FROM operadores WHERE id = gerencia_id;
    SELECT hash_clave INTO hash_conserje FROM operadores WHERE id = conserje_id;
    IF hash_gerencia <> 'hash-g' THEN RAISE EXCEPTION 'Cambio la clave de la gerencia'; END IF;
    IF hash_conserje <> 'hash-c-restablecido' THEN RAISE EXCEPTION 'No quedo la clave restablecida del conserje'; END IF;
    IF (SELECT hash_clave FROM operadores WHERE id = conserje_otro) <> 'x' THEN
        RAISE EXCEPTION 'Cambio la clave de un usuario de otro establecimiento';
    END IF;

    RAISE NOTICE 'verify_categorias_perfil: categorias, tarifas por categoria y claves verificadas';
END $$;
ROLLBACK;
