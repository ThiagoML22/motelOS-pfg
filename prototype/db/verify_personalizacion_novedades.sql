-- Verifica la migracion 009 con el rol de la aplicacion, motel_app: la gerencia cambia la apariencia solo de su
-- establecimiento, y las novedades son de solo agregado, a nombre del usuario de la sesion, en su propia guardia y
-- aisladas por establecimiento. Falla con error si alguna garantia no se cumple. Corre en una transaccion que se
-- revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_personalizacion_novedades.sql
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    conserje_id integer;
    otro_conserje integer;
    guardia_id integer;
    nov integer;
    filas integer;
    bloqueado boolean;
BEGIN
    -- Datos del dueno: otro establecimiento; dos conserjes del 1 y una guardia abierta del primero.
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-nov', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave) VALUES ('verif.n1', 'Conserje', 'x')
    RETURNING id INTO conserje_id;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave) VALUES ('verif.n2', 'Otro conserje', 'x')
    RETURNING id INTO otro_conserje;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje_id, '06:00') RETURNING id INTO guardia_id;

    PERFORM set_config('app.operador_id', conserje_id::text, true);
    SET LOCAL ROLE motel_app;

    -- 1. Apariencia del propio establecimiento; el color se valida; la de otro no se toca.
    UPDATE establecimientos
       SET color_marca = '#b4235a', eslogan = 'Hola', aviso_por_vencer_min = 15, alertas_sonoras = true
     WHERE id = 1;
    bloqueado := false;
    BEGIN UPDATE establecimientos SET color_marca = 'rojo' WHERE id = 1;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se acepto un color de marca invalido'; END IF;
    bloqueado := false;
    BEGIN UPDATE establecimientos SET aviso_por_vencer_min = 500 WHERE id = 1;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se acepto un aviso de 500 minutos'; END IF;
    UPDATE establecimientos SET eslogan = 'ajeno' WHERE id = otro;
    GET DIAGNOSTICS filas = ROW_COUNT;
    IF filas <> 0 THEN RAISE EXCEPTION 'Se cambio la apariencia de otro establecimiento'; END IF;

    -- 2. Novedad propia en la guardia abierta propia.
    INSERT INTO novedades (operador_id, guardia_id, texto, importante)
    VALUES (conserje_id, guardia_id, 'Falta papel en la 4', true) RETURNING id INTO nov;

    -- 3. No se escribe a nombre de otro usuario.
    bloqueado := false;
    BEGIN INSERT INTO novedades (operador_id, texto) VALUES (otro_conserje, 'suplantada');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se escribio una novedad a nombre de otro usuario'; END IF;

    -- 4. Solo agregado: sin cambios ni bajas.
    bloqueado := false;
    BEGIN UPDATE novedades SET texto = 'cambiada' WHERE id = nov;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se modifico una novedad'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM novedades WHERE id = nov;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro una novedad'; END IF;

    -- 5. No se escribe en otro establecimiento.
    bloqueado := false;
    BEGIN INSERT INTO novedades (establecimiento_id, operador_id, texto) VALUES (otro, conserje_id, 'cruzada');
    EXCEPTION WHEN insufficient_privilege OR foreign_key_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se escribio una novedad en otro establecimiento'; END IF;

    -- 6. No en la guardia de otro conserje.
    PERFORM set_config('app.operador_id', otro_conserje::text, true);
    bloqueado := false;
    BEGIN INSERT INTO novedades (operador_id, guardia_id, texto) VALUES (otro_conserje, guardia_id, 'ajena');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se escribio una novedad en la guardia de otro conserje'; END IF;

    -- 7. Otro establecimiento no ve las novedades del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM novedades;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio las novedades de otro'; END IF;
    RAISE NOTICE 'verify_personalizacion_novedades: apariencia propia y novedades de solo agregado verificadas';
END $$;
ROLLBACK;
