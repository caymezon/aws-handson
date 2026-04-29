package com.example.webapp.controller;

import com.example.webapp.repository.ItemRepository;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class ItemController {

    private final ItemRepository itemRepository;

    public ItemController(ItemRepository itemRepository) {
        this.itemRepository = itemRepository;
    }

    @GetMapping("/")
    public String index(Model model) {
        model.addAttribute("items", itemRepository.findAll());
        return "index";
    }

    @PostMapping("/items/add")
    public String add(@RequestParam String name) {
        if (name != null && !name.isBlank()) {
            itemRepository.add(name.trim());
        }
        return "redirect:/";
    }

    @PostMapping("/items/delete/{id}")
    public String delete(@PathVariable Long id) {
        itemRepository.delete(id);
        return "redirect:/";
    }
}
