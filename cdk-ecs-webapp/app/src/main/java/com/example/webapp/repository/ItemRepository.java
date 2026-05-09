package com.example.webapp.repository;

import com.example.webapp.model.Item;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public class ItemRepository {

    private final JdbcTemplate jdbc;

    public ItemRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Item> findAll() {
        return jdbc.query(
            "SELECT id, name, created_at FROM items ORDER BY created_at DESC",
            rowMapper()
        );
    }

    public void add(String name) {
        jdbc.update("INSERT INTO items (name) VALUES (?)", name);
    }

    public void delete(Long id) {
        jdbc.update("DELETE FROM items WHERE id = ?", id);
    }

    private RowMapper<Item> rowMapper() {
        return (rs, rowNum) -> new Item(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getTimestamp("created_at").toLocalDateTime()
        );
    }
}
